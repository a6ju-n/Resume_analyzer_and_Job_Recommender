"""Profile page, built entirely from the user's stored resumes (there is no login yet)."""
from flask import Blueprint, render_template, request

from database.db import db
from database.models import Resume
from routes.resume import refresh_derived
from services.skills import LANGUAGE_KINDS, TOOLING_KINDS, kind_of

bp = Blueprint("profile", __name__, url_prefix="/profile")


@bp.route("/")
def index():
    resumes = Resume.query.order_by(Resume.created_at.desc()).all()
    if not resumes:
        return render_template("profile.html", resume=None, resumes=[])

    # Which resume the profile is built from: ?resume_id=, else the newest usable one.
    chosen = None
    wanted = request.args.get("resume_id", type=int)
    if wanted:
        chosen = next((r for r in resumes if r.id == wanted), None)
    if chosen is None:
        chosen = next((r for r in resumes if r.extracted_text and not r.is_scanned), resumes[0])

    refresh_derived(chosen)
    parsed   = chosen.parsed_data or {}
    analysis = chosen.ai_analysis or {}
    detected = parsed.get("detected_skills", [])

    scores = [(r.ai_analysis or {}).get("quality_score") for r in resumes]
    scores = [s for s in scores if s is not None]

    name = (parsed.get("name") or "").strip()
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"

    return render_template(
        "profile.html",
        resume=chosen,
        resumes=resumes,
        parsed=parsed,
        analysis=analysis,
        name=name,
        initials=initials,
        languages=[s for s in detected if kind_of(s) in LANGUAGE_KINDS],
        tools=[s for s in detected if kind_of(s) in TOOLING_KINDS],
        concepts=[s for s in detected if kind_of(s) == "concept"],
        jobs=(chosen.job_recommendations or [])[:3],
        stats={
            "total": len(resumes),
            "scored": len(scores),
            "avg_score": round(sum(scores) / len(scores)) if scores else None,
            "latest_score": analysis.get("quality_score"),
        },
    )
