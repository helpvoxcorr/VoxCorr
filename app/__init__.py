# app/__init__.py
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from app.config import Config
import threading                                    # ← nouveau
from datetime import datetime, timezone, timedelta  # ← nouveau (timedelta manquait)

db            = SQLAlchemy()
migrate       = Migrate()
login_manager = LoginManager()
csrf          = CSRFProtect()

login_manager.login_view             = 'auth.login'
login_manager.login_message          = 'Connectez-vous pour accéder à cette page.'
login_manager.login_message_category = 'warning'

# ── État partagé pour la purge périodique ─────────────────────────────────────
_purge_lock    = threading.Lock()
_last_purge_at = None                              # datetime UTC de la dernière purge
# ─────────────────────────────────────────────────────────────────────────────

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models

    from app.blueprints.auth    import auth_bp
    from app.blueprints.teacher import teacher_bp
    from app.blueprints.public  import public_bp
    from app.blueprints.pages   import pages_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(pages_bp)

    @app.route('/ping')
    def ping():
        return {"status": "ok", "app": "VoxCorr"}

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app.before_request
    def before_request_hooks():
        """
        Regroupe les tâches avant-requête :
        1. Expiration session admin après 30 min.
        2. Purge automatique des vieux logs (toutes les 6h max).
        """
        from flask import session

        # ── 1. Expiration session admin ───────────────────────────────────────
        unlocked_at = session.get('admin_unlocked_at')
        if unlocked_at:
            unlocked_dt = datetime.fromisoformat(unlocked_at)
            if datetime.now(timezone.utc) - unlocked_dt > timedelta(minutes=30):
                session.pop('admin_unlocked',    None)
                session.pop('admin_unlocked_at', None)

        # ── 2. Purge périodique (toutes les 6h) ───────────────────────────────
        global _last_purge_at
        now = datetime.now(timezone.utc)

        if _last_purge_at is None or (now - _last_purge_at) >= timedelta(hours=6):
            # Le verrou évite les doubles exécutions sur workers multi-thread
            acquired = _purge_lock.acquire(blocking=False)
            if acquired:
                try:
                    # Double-check après acquisition du verrou
                    if _last_purge_at is None or (now - _last_purge_at) >= timedelta(hours=6):
                        _last_purge_at = now
                        _run_purge(app)
                finally:
                    _purge_lock.release()


def _run_purge(app):
    """
    Supprime :
    - les AccessLog de plus de 6 mois (RGPD)
    - les Correction en statut 'draft' de plus de 30 jours
    Exécuté dans le contexte applicatif existant (pas de thread séparé).
    """
    from app.models import AccessLog, Correction
    now     = datetime.now(timezone.utc)
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
                Correction.status    == 'draft',
                Correction.created_at < cutoff_drafts,
            )
            .delete(synchronize_session=False)
        )
        db.session.commit()
        app.logger.info(f'[purge] {n_logs} access_logs + {n_drafts} drafts supprimés')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'[purge] Échec : {e}')