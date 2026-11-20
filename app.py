"""Application factory and entry point."""
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from config import Config
from database.db import db

csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)

    from database import models  # noqa: F401  (register models)
    from routes.dashboard import bp as dashboard_bp
    from routes.main import bp as main_bp
    from routes.profile import bp as profile_bp
    from routes.resume import bp as resume_bp
    from routes.settings import bp as settings_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(resume_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(settings_bp)

    app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True)
    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
