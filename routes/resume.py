"""
Resume blueprint — handles upload, text extraction, AI analysis,
job recommendations, history, and deletion.

URL prefix: /resume
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from database.db import db
from database.models import Resume
from services import extractor as ext
from services import job_matcher
from services import ollama_client as ollama

bp = Blueprint("resume", __name__, url_prefix="/resume")

ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_MB = 5  # hard cap; config also enforces this at Flask level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _file_ext(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower()


def _run_analysis(resume: Resume) -> None:
    """
    Extract text, parse sections, call Ollama, store results.
    Called synchronously inside the request so the user sees the results
    immediately (acceptable for a local dev tool).
    """
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    filepath = Path(upload_folder) / resume.stored_filename

    # 1 — text extraction
    try:
        raw_text, is_scanned = ext.extract_text(filepath, resume.file_type)
    except Exception as exc:
        resume.analysis_status = "error"
        resume.analysis_error  = f"Text extraction failed: {exc}"
        db.session.commit()
        return

    resume.extracted_text = raw_text
    resume.is_scanned     = is_scanned

    if is_scanned:
        resume.analysis_status = "error"
        resume.analysis_error  = (
            "This PDF appears to be a scanned image. "
            "Please upload a text-based PDF or convert it first."
        )
        db.session.commit()
        return

    # 2 — section parsing
    parsed = ext.parse_resume_sections(raw_text)
    resume.parsed_data = parsed

    # 3 — Ollama analysis
    resume.analysis_status = "analysing"
    db.session.commit()

    # 3 — job matching (rule-based, so it works even if Ollama is offline)
    resume.job_recommendations = job_matcher.recommend_jobs(
        raw_text, ext.get_skills_section(raw_text)
    )
    db.session.commit()

    # 4 — Ollama analysis (quality score and advice)
    analysis = ollama.analyse_resume(parsed, raw_text)
    resume.ai_analysis = analysis

    if analysis.get("error"):
        resume.analysis_status = "error"
        resume.analysis_error  = analysis.get("message", "AI analysis failed.")
    else:
        resume.analysis_status = "done"

    db.session.commit()


def refresh_derived(resume: Resume) -> None:
    """
    Recompute the parsed skills and job matches from the stored resume text.
    Cheap (no AI), and it corrects resumes analysed by older versions.
    """
    if not resume.extracted_text or resume.is_scanned:
        return
    text   = resume.extracted_text
    parsed = ext.parse_resume_sections(text)
    jobs   = job_matcher.recommend_jobs(text, ext.get_skills_section(text))
    if parsed != resume.parsed_data or jobs != resume.job_recommendations:
        resume.parsed_data = parsed
        resume.job_recommendations = jobs
        db.session.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        f = request.files.get("resume_file")

        if not f or f.filename == "":
            flash("No file selected.", "error")
            return redirect(url_for("resume.upload"))

        if not _allowed(f.filename):
            flash("Only PDF and DOCX files are accepted.", "error")
            return redirect(url_for("resume.upload"))

        # Size guard (read up to MAX_MB+1 bytes to detect oversize)
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        limit = current_app.config.get("MAX_CONTENT_LENGTH", MAX_MB * 1024 * 1024)
        if size > limit:
            flash(
                f"File is too large. Maximum allowed size is {limit // (1024*1024)} MB.",
                "error",
            )
            return redirect(url_for("resume.upload"))

        file_ext  = _file_ext(f.filename)
        stored_fn = f"{uuid.uuid4().hex}.{file_ext}"
        save_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_fn
        f.save(str(save_path))

        resume = Resume(
            user_id           = None,         # TODO: set to current_user.id when auth added
            original_filename = f.filename,
            stored_filename   = stored_fn,
            file_type         = file_ext,
            file_size_bytes   = size,
            analysis_status   = "pending",
        )
        db.session.add(resume)
        db.session.commit()

        # Run analysis synchronously
        _run_analysis(resume)

        flash("Resume uploaded and analysed successfully.", "success")
        return redirect(url_for("resume.results", resume_id=resume.id))

    return render_template("resume/upload.html")


@bp.route("/<int:resume_id>/results")
def results(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    refresh_derived(resume)
    return render_template("resume/results.html", resume=resume)


@bp.route("/<int:resume_id>/jobs")
def jobs(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    refresh_derived(resume)
    return render_template("resume/jobs.html", resume=resume, all_roles=job_matcher.role_names())


@bp.route("/<int:resume_id>/select-role", methods=["POST"])
def select_role(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    role = request.form.get("role", "").strip()
    if role:
        resume.selected_role = role
        db.session.commit()
        flash("Target role set to: " + role, "success")
    return redirect(url_for("resume.jobs", resume_id=resume_id))


@bp.route("/<int:resume_id>/analyse", methods=["POST"])
def reanalyse(resume_id: int):
    """Re-trigger analysis for a resume (e.g. after Ollama comes online)."""
    resume = db.get_or_404(Resume, resume_id)
    resume.analysis_status = "pending"
    resume.analysis_error  = None
    resume.ai_analysis     = None
    db.session.commit()
    _run_analysis(resume)
    flash("Re-analysis complete.", "success")
    return redirect(url_for("resume.results", resume_id=resume_id))


@bp.route("/<int:resume_id>/delete", methods=["POST"])
def delete(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    # Remove the stored file
    filepath = Path(current_app.config["UPLOAD_FOLDER"]) / resume.stored_filename
    try:
        filepath.unlink(missing_ok=True)
    except Exception as exc:
        current_app.logger.warning("Could not delete file %s: %s", filepath, exc)

    db.session.delete(resume)
    db.session.commit()
    flash("Resume deleted.", "success")
    return redirect(url_for("resume.history"))


@bp.route("/history")
def history():
    # TODO: filter by current_user.id when auth is added
    resumes = Resume.query.order_by(Resume.created_at.desc()).all()
    return render_template("resume/history.html", resumes=resumes)


# ---------------------------------------------------------------------------
# AJAX endpoint: check analysis status (for polling from the results page)
# ---------------------------------------------------------------------------

@bp.route("/<int:resume_id>/status")
def status(resume_id: int):
    resume = db.get_or_404(Resume, resume_id)
    return jsonify(
        status=resume.analysis_status,
        error=resume.analysis_error,
    )
