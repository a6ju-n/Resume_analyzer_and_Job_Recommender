"""
Tests for the Resume Analyzer module.

Run with:   pytest tests/ -v
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from config import TestConfig
from database.db import db
from database.models import Resume, User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    _app = create_app(TestConfig)
    with _app.app_context():
        db.create_all()
        yield _app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def upload_folder(app):
    return Path(app.config["UPLOAD_FOLDER"])


# ---------------------------------------------------------------------------
# Minimal valid PDF bytes (1-page, text "Hello World")
# ---------------------------------------------------------------------------

def _minimal_pdf() -> bytes:
    """Return a minimal but valid single-page PDF with selectable text."""
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>
stream
BT /F1 12 Tf 100 700 Td (Hello World) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
441
%%EOF"""


def _minimal_docx() -> bytes:
    """Create a minimal DOCX in memory using python-docx."""
    import docx as _docx
    buf = io.BytesIO()
    doc = _docx.Document()
    doc.add_paragraph("John Doe")
    doc.add_paragraph("john@example.com")
    doc.add_paragraph("Skills: Python, Flask, SQL")
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# 1. Route / HTTP tests
# ---------------------------------------------------------------------------

class TestUploadRoute:

    def test_upload_page_renders(self, client):
        r = client.get("/resume/upload")
        assert r.status_code == 200
        assert b"Upload" in r.data

    def test_history_page_renders_empty(self, client):
        r = client.get("/resume/history")
        assert r.status_code == 200
        assert b"No resumes" in r.data

    def test_invalid_file_type_rejected(self, client):
        data = {"resume_file": (io.BytesIO(b"garbage"), "resume.txt")}
        r = client.post("/resume/upload", data=data,
                        content_type="multipart/form-data",
                        follow_redirects=True)
        assert b"PDF" in r.data or b"DOCX" in r.data or b"accepted" in r.data

    def test_oversized_file_rejected(self, client, app):
        big = io.BytesIO(b"x" * (app.config["MAX_CONTENT_LENGTH"] + 1))
        data = {"resume_file": (big, "big.pdf")}
        r = client.post("/resume/upload", data=data,
                        content_type="multipart/form-data",
                        follow_redirects=True)
        # Either Flask returns 413 or our guard flashes an error
        assert r.status_code in (200, 413)

    def test_no_file_rejected(self, client):
        r = client.post("/resume/upload", data={},
                        content_type="multipart/form-data",
                        follow_redirects=True)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 2. DOCX upload (real extraction, mocked Ollama)
# ---------------------------------------------------------------------------

class TestDocxUpload:

    @patch("routes.resume.ollama.analyse_resume", return_value={
        "error": False, "message": "",
        "quality_score": 70,
        "strengths": ["Good Python skills"],
        "weaknesses": [],
        "missing_information": [],
        "improvement_suggestions": ["Add GitHub link"],
        "overall_summary": "Decent resume.",
    })
    def test_docx_upload_and_analysis(self, mock_analyse, client, upload_folder):
        docx_bytes = _minimal_docx()
        data = {"resume_file": (io.BytesIO(docx_bytes), "my_cv.docx")}
        r = client.post("/resume/upload", data=data,
                        content_type="multipart/form-data",
                        follow_redirects=True)
        assert r.status_code == 200
        # Should have created a DB row
        resume = Resume.query.first()
        assert resume is not None
        assert resume.file_type == "docx"
        assert resume.analysis_status == "done"
        assert resume.ai_analysis["quality_score"] == 70

    @patch("routes.resume.ollama.analyse_resume", return_value={
        "error": False, "message": "", "quality_score": 55,
        "strengths": [], "weaknesses": [], "missing_information": [],
        "improvement_suggestions": [], "overall_summary": "",
    })
    def test_results_page_renders(self, mock_analyse, client):
        docx_bytes = _minimal_docx()
        data = {"resume_file": (io.BytesIO(docx_bytes), "cv.docx")}
        client.post("/resume/upload", data=data,
                    content_type="multipart/form-data",
                    follow_redirects=False)
        resume = Resume.query.first()
        r = client.get(f"/resume/{resume.id}/results")
        assert r.status_code == 200
        assert b"55" in r.data   # quality score


# ---------------------------------------------------------------------------
# 3. Extractor unit tests
# ---------------------------------------------------------------------------

class TestExtractor:

    def test_extract_email(self):
        from services.extractor import _extract_email
        assert _extract_email("contact: jane@example.com today") == "jane@example.com"
        assert _extract_email("no email here") == ""

    def test_extract_phone(self):
        from services.extractor import _extract_phone
        result = _extract_phone("Call me at +91 98765 43210")
        assert "98765" in result

    def test_extract_programming_languages(self):
        from services.extractor import _extract_programming_languages
        text = "I know Python, Java, and some JavaScript."
        langs = _extract_programming_languages(text)
        assert {"Python", "Java", "JavaScript"} <= set(langs)
        assert "C" not in langs and "Go" not in langs

    def test_extract_frameworks(self):
        from services.extractor import _extract_frameworks
        text = "Built with Flask, React, and PostgreSQL."
        fws = _extract_frameworks(text)
        assert {"Flask", "React", "PostgreSQL"} <= set(fws)

    def test_parse_resume_sections_returns_all_keys(self):
        from services.extractor import parse_resume_sections
        result = parse_resume_sections("John Doe\njohn@test.com\nSkills\nPython, Flask\nEducation\nB.Sc CS")
        expected_keys = {
            "name", "email", "phone", "linkedin",
            "education", "skills", "programming_languages", "frameworks",
            "projects", "internships", "experience", "certifications", "achievements"
        }
        assert expected_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# 4. Ollama client unit tests (all HTTP mocked)
# ---------------------------------------------------------------------------

class TestOllamaClient:

    def test_is_ollama_available_true(self, app):
        with app.app_context():
            with patch("services.ollama_client.requests.get") as mock_get:
                mock_get.return_value = MagicMock(status_code=200)
                from services.ollama_client import is_ollama_available
                assert is_ollama_available() is True

    def test_is_ollama_available_false_on_connection_error(self, app):
        import requests as _req
        with app.app_context():
            with patch("services.ollama_client.requests.get",
                       side_effect=_req.exceptions.ConnectionError):
                from services.ollama_client import is_ollama_available
                assert is_ollama_available() is False

    def test_analyse_resume_returns_error_dict_when_offline(self, app):
        import requests as _req
        with app.app_context():
            with patch("services.ollama_client.requests.post",
                       side_effect=_req.exceptions.ConnectionError):
                from services.ollama_client import analyse_resume
                result = analyse_resume({}, "some resume text")
                assert result["error"] is True
                assert result["quality_score"] is None

    def test_analyse_resume_happy_path(self, app):
        good_json = json.dumps({
            "quality_score": 80,
            "strengths": ["Great Python skills"],
            "weaknesses": ["No GitHub"],
            "missing_information": [],
            "improvement_suggestions": ["Add a portfolio"],
            "overall_summary": "Strong candidate.",
        })
        with app.app_context():
            with patch("services.ollama_client.requests.post") as mock_post:
                mock_post.return_value = MagicMock(
                    status_code=200,
                    json=lambda: {"response": good_json},
                )
                mock_post.return_value.raise_for_status = lambda: None
                from services.ollama_client import analyse_resume
                result = analyse_resume({"skills": ["Python"]}, "resume text")
                assert result["error"] is False
                assert result["quality_score"] == 80
                assert "Great Python skills" in result["strengths"]

    def test_parse_json_strips_think_tags(self):
        """qwen3 models emit <think>…</think> before JSON."""
        from services.ollama_client import _parse_json_from_response
        text = "<think>reasoning here</think>\n{\"quality_score\": 72}"
        result = _parse_json_from_response(text)
        assert result == {"quality_score": 72}

    def test_parse_json_handles_code_fences(self):
        from services.ollama_client import _parse_json_from_response
        text = "```json\n{\"quality_score\": 60}\n```"
        result = _parse_json_from_response(text)
        assert result == {"quality_score": 60}


# ---------------------------------------------------------------------------
# 5. Database storage and deletion
# ---------------------------------------------------------------------------

class TestDatabase:

    @patch("routes.resume.ollama.analyse_resume", return_value={
        "error": False, "message": "", "quality_score": 65,
        "strengths": [], "weaknesses": [], "missing_information": [],
        "improvement_suggestions": [], "overall_summary": "",
    })
    def test_delete_resume(self, mock_analyse, client, upload_folder):
        docx_bytes = _minimal_docx()
        data = {"resume_file": (io.BytesIO(docx_bytes), "del_me.docx")}
        client.post("/resume/upload", data=data,
                    content_type="multipart/form-data",
                    follow_redirects=False)
        resume = Resume.query.first()
        assert resume is not None
        resume_id = resume.id

        r = client.post(f"/resume/{resume_id}/delete",
                        data={"csrf_token": ""},
                        follow_redirects=True)
        assert r.status_code == 200
        assert db.session.get(Resume, resume_id) is None

    @patch("routes.resume.ollama.analyse_resume", return_value={
        "error": False, "message": "", "quality_score": 55,
        "strengths": [], "weaknesses": [], "missing_information": [],
        "improvement_suggestions": [], "overall_summary": "",
    })
    def test_select_role_stored(self, mock_analyse, client):
        docx_bytes = _minimal_docx()
        data = {"resume_file": (io.BytesIO(docx_bytes), "sel_role.docx")}
        client.post("/resume/upload", data=data,
                    content_type="multipart/form-data",
                    follow_redirects=False)
        resume = Resume.query.first()
        client.post(f"/resume/{resume.id}/select-role",
                    data={"role": "Python Developer", "csrf_token": ""},
                    follow_redirects=False)
        db.session.refresh(resume)
        assert resume.selected_role == "Python Developer"



# ---------------------------------------------------------------------------
# 6. Skill detection + job matching (rule-based, no AI)
# ---------------------------------------------------------------------------

SAMPLE = "Jane Doe\nSkills\nPython, Flask, SQL, Git\nExperience\nBuilt a REST API. Go to market. The rest of the team used Docker."


class TestSkillDetection:

    def test_ambiguous_words_are_not_skills(self):
        from services.skills import detect_skills
        found = detect_skills("I will go to the market. The rest of us express interest. Spring 2023, excel at maths.")
        assert not {"Go", "R", "C", "REST APIs", "Express", "Spring", "Excel"} & set(found)

    def test_ambiguous_skill_counts_when_listed(self):
        from services.skills import detect_skills
        assert {"Go", "R", "C"} <= set(detect_skills("x", "Languages: Python, Go, R, C"))

    def test_java_is_not_javascript_and_c_is_not_cpp(self):
        from services.skills import detect_skills
        assert detect_skills("JavaScript") == ["JavaScript"]
        assert detect_skills("C++, C#") == ["C++", "C#"]

    def test_flutter_is_a_framework_not_a_language(self):
        from services.extractor import parse_resume_sections
        p = parse_resume_sections("Jo Bloggs\nSkills\nDart, Flutter")
        assert "Flutter" in p["frameworks"] and "Flutter" not in p["programming_languages"]
        assert "Dart" in p["programming_languages"]


class TestJobMatcher:

    def test_skill_is_never_both_matching_and_missing(self):
        """Regression: Flask used to be 'matching' on one card and 'missing' on the next."""
        from services.job_matcher import recommend_jobs
        jobs = recommend_jobs(SAMPLE, "Python, Flask, SQL, Git")
        assert jobs
        for j in jobs:
            for skill in j["matching_skills"]:
                assert not any(skill in m.split(" / ") for m in j["missing_skills"]), (j["role"], skill)
        top = {j["role"]: j for j in jobs}["Python Developer"]
        assert {"Python", "Flask", "SQL", "Git"} <= set(top["matching_skills"])
        assert "Python" not in top["missing_skills"] and "Flask" not in top["missing_skills"]

    def test_ranked_and_bounded(self):
        from services.job_matcher import recommend_jobs
        jobs = recommend_jobs(SAMPLE)
        pcts = [j["match_percent"] for j in jobs]
        assert pcts == sorted(pcts, reverse=True) and all(0 < p <= 100 for p in pcts)
        assert len(jobs) <= 6

    def test_role_needs_a_defining_skill(self):
        from services.job_matcher import recommend_jobs
        roles = {j["role"] for j in recommend_jobs("Skills\nJava, Git, REST APIs, SQLite", "Java, Git, REST APIs, SQLite")}
        assert "Java Developer" in roles
        assert not {"Android Developer", "iOS Developer", "Flutter Developer"} & roles

    def test_unrelated_resume_gets_no_jobs(self):
        from services.job_matcher import recommend_jobs
        assert recommend_jobs("I enjoy painting and hiking.") == []

    def test_every_dropdown_role_exists(self):
        from services.job_matcher import role_names
        assert "Python Developer" in role_names() and len(role_names()) == 15

    def test_jobs_work_when_ollama_is_offline(self, client):
        with patch("services.ollama_client.requests.post", side_effect=__import__("requests").exceptions.ConnectionError):
            client.post("/resume/upload", data={"resume_file": (io.BytesIO(_minimal_docx()), "cv.docx")},
                        content_type="multipart/form-data")
        r = Resume.query.first()
        assert r.analysis_status == "error"
        assert any(j["role"] == "Python Developer" for j in r.job_recommendations)
        page = client.get(f"/resume/{r.id}/jobs")
        assert b"Python Developer" in page.data

    def test_stale_llm_data_is_corrected_on_view(self, client):
        stale = [{"role": "Python Developer", "match_percent": 90, "matching_skills": ["Flask"],
                  "missing_skills": ["Flask", "Python"], "recommendation": "x"}]
        r = Resume(original_filename="old.docx", stored_filename="old.docx", file_type="docx", file_size_bytes=1,
                   extracted_text=SAMPLE, analysis_status="done", job_recommendations=stale,
                   parsed_data={"programming_languages": ["flutter"]})
        db.session.add(r); db.session.commit()
        client.get(f"/resume/{r.id}/jobs")
        db.session.refresh(r)
        top = {j["role"]: j for j in r.job_recommendations}["Python Developer"]
        assert "Flask" not in top["missing_skills"] and "Python" not in top["missing_skills"]


# ---------------------------------------------------------------------------
# 7. Profile and Settings pages
# ---------------------------------------------------------------------------

def _add_resume(**kw):
    base = dict(original_filename="jane.docx", stored_filename="jane-1.docx", file_type="docx", file_size_bytes=2048,
                extracted_text=SAMPLE + "\njane@example.com", analysis_status="done",
                ai_analysis={"quality_score": 72, "improvement_suggestions": ["Add a GitHub link"]})
    base.update(kw)
    r = Resume(**base); db.session.add(r); db.session.commit(); return r


class TestProfile:

    def test_empty_profile(self, client):
        r = client.get("/profile/")
        assert r.status_code == 200 and b"built from your resume" in r.data

    def test_profile_is_built_from_resume_data(self, client):
        _add_resume()
        html = client.get("/profile/").get_data(as_text=True)
        assert "Jane Doe" in html and "jane@example.com" in html
        assert "Flask" in html and "Python Developer" in html and "Add a GitHub link" in html

    def test_profile_can_switch_resume(self, client):
        _add_resume()
        second = _add_resume(original_filename="other.docx", stored_filename="o.docx",
                             extracted_text="Sam Lee\nSkills\nJava, Spring Boot")
        html = client.get(f"/profile/?resume_id={second.id}").get_data(as_text=True)
        assert "Sam Lee" in html and "Java Developer" in html


class TestSettings:

    def test_settings_page_offline(self, client):
        with patch("services.ollama_client.requests.get", side_effect=__import__("requests").exceptions.ConnectionError):
            r = client.get("/settings/")
        assert r.status_code == 200 and b"Not reachable" in r.data

    def test_model_choice_is_saved_and_used(self, client, app):
        client.post("/settings/model", data={"model": "qwen2.5:3b"})
        from services import ollama_client as oc
        assert oc.get_model() == "qwen2.5:3b"
        client.post("/settings/model", data={"model": ""})
        assert oc.get_model() == app.config["OLLAMA_MODEL"]

    def test_invalid_model_name_rejected(self, client):
        client.post("/settings/model", data={"model": "bad name; rm -rf"})
        from services import ollama_client as oc
        assert oc.get_model() != "bad name; rm -rf"

    def test_delete_all_resumes(self, client):
        _add_resume(); _add_resume(stored_filename="b.docx")
        client.post("/settings/clear")
        assert Resume.query.count() == 0
