"""
Rule-based job recommender.

Every role has a list of required skills. A resume's skills are detected once
(services.skills) and compared against each role, so:

  * a skill is either "matching" or "missing" for a role, never both;
  * the same resume always gives the same result;
  * it works even when Ollama is not running.

A role is only recommended when the resume has at least one of its "gate"
skills (its defining skills, e.g. Android for an Android Developer), so shared
skills like Git or Java alone never produce a misleading match.

A requirement is either a skill name or a tuple of alternatives
("React", "Angular", "Vue") that is satisfied by any one of them.
Core requirements are worth 2 points, bonus requirements 1 point.
"""
from __future__ import annotations

from typing import Any

from services.skills import detect_skills

Req = "str | tuple[str, ...]"

_SERVER_LANG = ("Python", "Java", "Node.js", "Go", "C#", "PHP")
_BACKEND_FW  = ("Flask", "Django", "FastAPI", "Spring Boot", "Express")
_FRONT_FW    = ("React", "Angular", "Vue")
_CLOUD       = ("AWS", "Azure", "GCP")

ROLES: dict[str, dict] = {
    "Python Developer": {
        "gate":  ("Python",),
        "core":  ["Python"],
        "bonus": [("Flask", "Django", "FastAPI"), "SQL", "Git", "REST APIs", "Testing"],
    },
    "Web Developer": {
        "core":  ["HTML", "CSS", "JavaScript"],
        "bonus": [_FRONT_FW, "Bootstrap", "Git", "REST APIs"],
    },
    "Frontend Developer": {
        "core":  ["HTML", "CSS", "JavaScript", _FRONT_FW],
        "bonus": ["TypeScript", ("Tailwind CSS", "Bootstrap"), "Git"],
    },
    "Backend Developer": {
        "core":  [_SERVER_LANG, "SQL"],
        "bonus": [_BACKEND_FW, "REST APIs", "Git", "Docker", ("PostgreSQL", "MySQL", "MongoDB")],
    },
    "Full-Stack Developer": {
        "core":  ["HTML", "CSS", "JavaScript", _SERVER_LANG, "SQL"],
        "bonus": [_FRONT_FW, _BACKEND_FW, "Git", "REST APIs", "Docker"],
    },
    "Software Developer": {
        "core":  [("Python", "Java", "C++", "C#", "JavaScript", "Go", "C"), "Data Structures", "Git"],
        "bonus": ["OOP", "SQL", "Testing", "Linux", "Agile"],
    },
    "Java Developer": {
        "gate":  ("Java",),
        "core":  ["Java"],
        "bonus": [("Spring Boot", "Spring"), "SQL", ("MySQL", "PostgreSQL"), "Git", "REST APIs", "Testing"],
    },
    "Flutter Developer": {
        "gate":  ("Flutter", "Dart"),
        "core":  ["Dart", "Flutter"],
        "bonus": ["Firebase", "REST APIs", "Git", ("Android", "iOS")],
    },
    "Android Developer": {
        "gate":  ("Android",),
        "core":  [("Java", "Kotlin"), "Android"],
        "bonus": ["Firebase", "REST APIs", "SQLite", "Git"],
    },
    "iOS Developer": {
        "gate":  ("iOS", "Swift"),
        "core":  ["Swift", "iOS"],
        "bonus": ["REST APIs", "Git", "Firebase"],
    },
    "Data Analyst": {
        "gate":  ("SQL", "Excel", "Tableau", "Power BI", "Data Analysis", "Pandas"),
        "core":  ["SQL", ("Excel", "Tableau", "Power BI"), ("Python", "R")],
        "bonus": ["Pandas", "Data Visualization", "Matplotlib", "Data Analysis", "Jupyter"],
    },
    "Data Scientist": {
        "gate":  ("Machine Learning", "Pandas", "NumPy", "scikit-learn"),
        "core":  ["Python", "Machine Learning", ("Pandas", "NumPy")],
        "bonus": ["scikit-learn", "SQL", "Matplotlib", "Deep Learning", "Jupyter"],
    },
    "Machine Learning Engineer": {
        "gate":  ("Machine Learning", "TensorFlow", "PyTorch", "Keras", "scikit-learn", "Deep Learning"),
        "core":  ["Python", "Machine Learning", ("TensorFlow", "PyTorch", "Keras", "scikit-learn")],
        "bonus": ["Deep Learning", "NLP", "Docker", "Git", _CLOUD],
    },
    "DevOps Engineer": {
        "gate":  ("Docker", "CI/CD", "Kubernetes", "Terraform"),
        "core":  ["Linux", "Docker", "CI/CD", "Git"],
        "bonus": ["Kubernetes", _CLOUD, "Terraform", "Bash", "Python"],
    },
    "Cloud Engineer": {
        "gate":  _CLOUD,
        "core":  [_CLOUD, "Linux"],
        "bonus": ["Docker", "Kubernetes", "Terraform", "Bash", "Python", "CI/CD"],
    },
}

MAX_RESULTS = 6


def role_names() -> list[str]:
    return list(ROLES)


def _alts(req) -> tuple[str, ...]:
    return req if isinstance(req, tuple) else (req,)


def _label(req) -> str:
    return " / ".join(_alts(req)[:3])


def _score_role(role: str, spec: dict, have: set[str]) -> dict[str, Any] | None:
    matching: list[str] = []
    missing_core: list[str] = []
    missing_bonus: list[str] = []
    earned = total = core_hits = 0

    for weight, key in ((2, "core"), (1, "bonus")):
        for req in spec[key]:
            total += weight
            hit = [s for s in _alts(req) if s in have]
            if hit:
                earned += weight
                core_hits += key == "core"
                matching.extend(s for s in hit if s not in matching)
            else:
                (missing_core if key == "core" else missing_bonus).append(_label(req))

    gate = spec.get("gate")
    if (gate and not have.intersection(gate)) or core_hits == 0:
        return None     # nothing in the resume points at this role

    missing = (missing_core + missing_bonus)[:6]
    n_reqs = len(spec["core"]) + len(spec["bonus"])
    n_hit = n_reqs - len(missing_core) - len(missing_bonus)
    if missing:
        advice = (f"You already match {n_hit} of {n_reqs} key skills for this role. "
                  f"Next, learn {' and '.join(missing[:2])}.")
    else:
        advice = "Your resume covers every key skill we look for in this role."

    return {
        "role": role,
        "match_percent": round(100 * earned / total),
        "matching_skills": matching,
        "missing_skills": missing,
        "recommendation": advice,
        "_missing_core": len(missing_core),
    }


def recommend_jobs(raw_text: str, skills_section: str = "") -> list[dict[str, Any]]:
    """Rank roles for a resume. Returns [] when no known skills are found."""
    have = set(detect_skills(raw_text or "", skills_section))
    scored = [r for role, spec in ROLES.items() if (r := _score_role(role, spec, have))]
    scored.sort(key=lambda r: (-r["match_percent"], r["_missing_core"], r["role"]))
    for r in scored:
        r.pop("_missing_core")
    return scored[:MAX_RESULTS]
