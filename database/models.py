"""ORM models: User and Resume (with its AI analysis and job recommendations)."""
from datetime import datetime, timezone

from database.db import db


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)

    resumes = db.relationship("Resume", back_populates="user", cascade="all, delete-orphan")


class Resume(TimestampMixin, db.Model):
    """Stores an uploaded resume and all derived AI artefacts."""
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    # --- file metadata ---
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename   = db.Column(db.String(255), nullable=False, unique=True)
    file_type         = db.Column(db.String(10), nullable=False)   # "pdf" | "docx"
    file_size_bytes   = db.Column(db.Integer, nullable=False, default=0)

    # --- extracted content ---
    extracted_text = db.Column(db.Text, nullable=True)
    parsed_data    = db.Column(db.JSON, nullable=True)   # name, email, phone, skills …
    is_scanned     = db.Column(db.Boolean, default=False, nullable=False)

    # --- AI artefacts ---
    ai_analysis          = db.Column(db.JSON, nullable=True)
    job_recommendations  = db.Column(db.JSON, nullable=True)
    selected_role        = db.Column(db.String(100), nullable=True)

    # --- workflow state ---
    # "pending" → "analysing" → "done" | "error"
    analysis_status  = db.Column(db.String(20), default="pending", nullable=False)
    analysis_error   = db.Column(db.Text, nullable=True)

    user = db.relationship("User", back_populates="resumes")

    # ------------------------------------------------------------------ helpers
    @property
    def display_name(self):
        return self.original_filename

    @property
    def status_badge(self):
        mapping = {
            "pending":   ("secondary", "Pending"),
            "analysing": ("warning",   "Analysing…"),
            "done":      ("success",   "Done"),
            "error":     ("danger",    "Error"),
        }
        return mapping.get(self.analysis_status, ("secondary", self.analysis_status))


class AppSetting(db.Model):
    """Small key/value store for preferences chosen on the Settings page."""
    __tablename__ = "app_settings"

    key   = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(255), nullable=True)

    @classmethod
    def get(cls, key: str, default=None):
        row = db.session.get(cls, key)
        return row.value if row and row.value else default

    @classmethod
    def set(cls, key: str, value) -> None:
        row = db.session.get(cls, key)
        if row is None:
            db.session.add(cls(key=key, value=value))
        else:
            row.value = value
        db.session.commit()
