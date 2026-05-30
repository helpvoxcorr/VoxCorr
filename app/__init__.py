# app/__init__.py
from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from app.config import Config
import threading

from datetime import datetime, timezone, timedelta
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
limiter = Limiter(key_func=get_remote_address, default_limits=[])

login_manager.login_view             = 'auth.login'
login_manager.login_message          = 'Connectez-vous pour accéder à cette page.'
login_manager.login_message_category = 'warning'

_purge_lock    = threading.Lock()
_last_purge_at = None

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app import models
    from app.blueprints.auth    import auth_bp
    from app.blueprints.teacher import teacher_bp
    from app.blueprints.public  import public_bp
    from app.blueprints.pages   import pages_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(pages_bp)

    # ── Gestionnaires d'erreurs ────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f'[500] {e}')
        return render_template('errors/500.html'), 500

    @app.route('/ping')
    def ping():
        return {"status": "ok", "app": "VoxCorr"}

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app.before_request
    def before_request_hooks():
        from flask import session

        # 1. Expiration session admin
        unlocked_at = session.get('admin_unlocked_at')
        if unlocked_at:
            unlocked_dt = datetime.fromisoformat(unlocked_at)
            if datetime.now(timezone.utc) - unlocked_dt > timedelta(minutes=30):
                session.pop('admin_unlocked',    None)
                session.pop('admin_unlocked_at', None)

        # 2. Purge périodique (toutes les 6h)
        global _last_purge_at
        now = datetime.now(timezone.utc)
        if _last_purge_at is None or (now - _last_purge_at) >= timedelta(hours=6):
            acquired = _purge_lock.acquire(blocking=False)
            if acquired:
                try:
                    if _last_purge_at is None or (now - _last_purge_at) >= timedelta(hours=6):
                        _last_purge_at = now
                        _run_purge(app)
                finally:
                    _purge_lock.release()

    # Migration automatique au démarrage
    # with app.app_context():
    #     from flask_migrate import upgrade as db_upgrade
    #     try:
    #         db_upgrade()
    #         app.logger.info('[migrate] flask db upgrade OK')
    #     except Exception as e:
    #         app.logger.error(f'[migrate] Erreur : {e}')
    return app  # ← INDISPENSABLE


def _run_purge(app):
    from app.models import AccessLog, Correction
    now           = datetime.now(timezone.utc)
    cutoff_logs   = now - timedelta(days=180)
    cutoff_drafts = now - timedelta(days=30)
    try:
        n_logs = (
            db.session.query(AccessLog)
            .filter(AccessLog.accessed_at < cutoff_logs)
            .delete(synchronize_session=False)
        )
        n_drafts = (
            db.session.query(Correction)
            .filter(
                Correction.status     == 'draft',
                Correction.created_at  < cutoff_drafts,
            )
            .delete(synchronize_session=False)
        )
        db.session.commit()
        app.logger.info(f'[purge] {n_logs} access_logs + {n_drafts} drafts supprimés')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'[purge] Échec : {e}')