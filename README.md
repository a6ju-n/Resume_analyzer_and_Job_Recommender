# Resume Analyzer & Job Recommender

A Flask web app that reads your resume (PDF or DOCX), scores its quality with a **local Llama model**, and recommends job roles that match the skills it finds. Everything runs on your own computer: your resume is never sent to an online service.

## Features

- **Resume upload:** PDF and DOCX, up to 5 MB (configurable). Text is extracted with PyMuPDF and python-docx.
- **Resume parsing:** pulls out name, email, phone, LinkedIn, education, experience, projects and skills.
- **AI quality analysis:** a local Llama model (through [Ollama](https://ollama.com)) gives a 0-100 quality score, strengths, weaknesses and specific improvement tips.
- **Job recommendations:** ranks 15 roles (Python, Web, Frontend, Backend, Full-Stack, Java, Android, Flutter, Data Analyst, Data Scientist, ML Engineer, DevOps, Cloud and more) with a match percentage, the skills you have and the skills you are missing.
- **Target role:** choose the role you are aiming for and it is saved to your profile.
- **Dashboard:** resumes uploaded, average quality score, best role match and recent resumes.
- **Profile:** built from your stored resume data: contact details, skills grouped by type, education, best matches and top improvements.
- **Settings:** check the Ollama connection, switch the AI model, see upload limits and delete all stored data.

## How it works

| Step | What happens | Uses AI? |
|------|--------------|----------|
| 1. Extract | Text is read from the PDF or DOCX | No |
| 2. Parse | Contact details, sections and skills are detected | No |
| 3. Job matching | Skills are compared with the required skills of each role | **No** (rule-based) |
| 4. Analysis | Quality score, strengths, weaknesses and suggestions | **Yes** (Llama via Ollama) |

Job matching is deliberately rule-based. A skill is either *matching* or *missing* for a role, never both, the same resume always gives the same result, and it still works when Ollama is not running. The Llama model is used only for the written analysis.

## Tech stack

- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-WTF (CSRF protection)
- **Database:** SQLite
- **Resume parsing:** PyMuPDF, python-docx
- **AI:** Llama models served locally by Ollama
- **Frontend:** Jinja templates, Bootstrap 5, Bootstrap Icons

## Getting started

### 1. Prerequisites

- Python 3.10 or newer
- [Ollama](https://ollama.com/download) (only needed for the AI analysis)

### 2. Install

```bash
git clone https://github.com/<your-username>/Resume_Analyzer.git
cd Resume_Analyzer

python -m venv env
# Windows
env\Scripts\activate
# macOS / Linux
source env/bin/activate

pip install -r requirements.txt
```

### 3. Set up the Llama model

Install Ollama, then download a model:

```bash
ollama pull llama3.2:3b
```

Which model should you use?

| Your computer | Suggested model |
|---------------|-----------------|
| 8 GB RAM | `llama3.2:3b` |
| 16 GB RAM | `llama3.1:8b` (or `qwen2.5:7b`) |
| Very low-end | `llama3.2:1b` (fastest, but analysis is shallow) |

Make sure Ollama is running (`ollama serve`, or start the Ollama app).

### 4. Configure

Copy the example environment file and edit it:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | dev key | Set this to a long random string |
| `DATABASE_URL` | SQLite file in `instance/` | Database location |
| `MAX_UPLOAD_MB` | `5` | Maximum resume size |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama is running |
| `OLLAMA_MODEL` | `llama3.2:1b` | Default model (can also be changed in Settings) |
| `OLLAMA_TIMEOUT` | `120` | Seconds to wait for the model. Raise it for bigger models |

### 5. Run

```bash
python app.py
```

Open <http://127.0.0.1:5000> in your browser.

## Using the app

1. Go to **Upload resume** and choose a PDF or DOCX.
2. Wait for the analysis. The page updates automatically.
3. Read your **quality score** and suggestions on the results page.
4. Open **Job Matches** to see ranked roles and your skill gaps, and pick a target role.
5. Check your **Profile** and **Dashboard** for the overall picture.

To change the AI model, open **Settings -> AI engine**, choose an installed model and click **Save model**. Use **Re-analyse** on a resume to run it again with the new model.

## Project structure

```
Resume_Analyzer/
├── app.py                  # Flask app factory
├── config.py               # Settings from environment variables
├── database/               # SQLAlchemy setup and models
├── routes/
│   ├── main.py             # Landing page, health check
│   ├── dashboard.py        # Dashboard statistics
│   ├── resume.py           # Upload, results, job matches, history
│   ├── profile.py          # Profile built from stored resumes
│   └── settings.py         # AI engine, uploads, data management
├── services/
│   ├── extractor.py        # PDF/DOCX text extraction and resume parsing
│   ├── skills.py           # Skill vocabulary and detection
│   ├── job_matcher.py      # Rule-based job recommendations
│   └── ollama_client.py    # Local Llama (Ollama) analysis
├── templates/              # Jinja templates
├── static/                 # CSS and JavaScript
├── tests/                  # pytest test suite
└── requirements.txt
```

## Customising job roles

Roles and their required skills live in `services/job_matcher.py`. Each role has **core** skills (worth 2 points), **bonus** skills (1 point) and a **gate**: at least one defining skill the resume must contain before the role is recommended. Add or edit a role there. New skills are added to the vocabulary in `services/skills.py`.

## Running the tests

```bash
python -m pytest
```

The tests do not need Ollama; the AI calls are mocked.

## Limitations

- Scanned (image-only) PDFs cannot be read, because there is no OCR.
- Skills are matched from a built-in vocabulary. A skill that is not in `services/skills.py` is not recognised.
- Match percentages and quality scores are guidance for improving your resume, not a prediction of hiring decisions.
- Small Llama models can give shallow or inconsistent advice. Use a larger model for better results.
- There is no login: the app is meant for one person on one computer.

## Privacy

Resumes are stored in the local `uploads/` folder and `instance/` database. Resume text is sent only to the Ollama server you configure (by default on your own machine). **Settings -> Delete all resumes** removes every file and record.

