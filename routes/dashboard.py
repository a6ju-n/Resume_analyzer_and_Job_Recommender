from flask import Blueprint, render_template

from database.models import Resume
from routes.resume import refresh_derived

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _build_stats():
    """Summarise all uploaded resumes. Returns None when nothing is uploaded."""
    resumes = Resume.query.order_by(Resume.created_at.desc()).all()
    if not resumes:
        return None
    for r in resumes:
        refresh_derived(r)      # corrects data saved by older versions

    done = [r for r in resumes if r.analysis_status == "done"]
    scores = [
        (r.ai_analysis or {}).get("quality_score")
        for r in done
    ]
    scores = [s for s in scores if s is not None]

    best_role, best_percent = None, None
    for r in done:
        for job in r.job_recommendations or []:
            pct = job.get("match_percent")
            if pct is not None and (best_percent is None or pct > best_percent):
                best_role, best_percent = job.get("role"), pct

    return {
        "total": len(resumes),
        "analysed": len(done),
        "avg_score": round(sum(scores) / len(scores)) if scores else None,
        "best_role": best_role,
        "best_percent": best_percent,
        "recent": resumes[:5],
    }


@bp.route("/")
def index():
    return render_template("dashboard.html", stats=_build_stats())
