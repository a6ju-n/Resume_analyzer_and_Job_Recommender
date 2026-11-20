"""Settings page: AI engine, upload limits, and stored-data management."""
import re
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from database.db import db
from database.models import AppSetting, Resume
from services import ollama_client as ollama

bp = Blueprint("settings", __name__, url_prefix="/settings")

_MODEL_RE = re.compile(r"^[\w.\-:/]{1,100}$")


@bp.route("/")
def index():
    online = ollama.is_ollama_available()
    resumes = Resume.query.all()
    return render_template(
        "settings.html",
        online=online,
        host=current_app.config["OLLAMA_HOST"],
        model=ollama.get_model(),
        default_model=current_app.config["OLLAMA_MODEL"],
        installed=ollama.list_models() if online else [],
        max_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        resume_count=len(resumes),
        storage_kb=round(sum(r.file_size_bytes or 0 for r in resumes) / 1024),
    )


@bp.route("/model", methods=["POST"])
def save_model():
    model = request.form.get("model", "").strip()
    if model and not _MODEL_RE.match(model):
        flash("That is not a valid model name.", "error")
    else:
        AppSetting.set("ollama_model", model or None)     # empty = back to the default
        flash(f"AI model set to {model}." if model else "AI model reset to the default.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/clear", methods=["POST"])
def clear_data():
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    count = 0
    for resume in Resume.query.all():
        try:
            (folder / resume.stored_filename).unlink(missing_ok=True)
        except OSError as exc:
            current_app.logger.warning("Could not delete %s: %s", resume.stored_filename, exc)
        db.session.delete(resume)
        count += 1
    db.session.commit()
    flash(f"Deleted {count} resume(s) and their files.", "success")
    return redirect(url_for("settings.index"))
