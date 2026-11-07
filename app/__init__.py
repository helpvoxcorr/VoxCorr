import os
from flask import Flask, redirect, url_for, render_template, session
from datetime import datetime, timezone, timedelta

from app.config import Config
from app.extensions import db, migrate, login_manager, csrf, limiter, socketio


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── Initialisation des extensions ──────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    allowed_origins = os.environ.get('SOCKETIO_CORS_ALLOWED', 'http://localhost:5000')
    socketio.init_app(app, cors_allowed_origins=allowed_origins.split(','))

    # ── Import des modèles (nécessaire pour que SQLAlchemy les connaisse) ──────
    from app import models

    # ── Enregistrement des Blueprints ──────────────────────────────────────────
    from app.blueprints.auth import auth_bp
    from app.blueprints.public import public_bp
    from app.blueprints.pages import pages_bp
    from app.blueprints.student import student_bp
    
    # Blueprints factorisés de l'espace enseignant
    from app.blueprints.teacher_crud import teacher_crud_bp
    from app.blueprints.teacher_corrections import teacher_corr_bp
    from app.blueprints.teacher_admin import teacher_admin_bp

    app.register_blueprint(student_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(teacher_crud_bp)
    app.register_blueprint(teacher_corr_bp)
    app.register_blueprint(teacher_admin_bp)
    from app.services.synthesis import clean_markup
    app.jinja_env.filters['synth'] = clean_markup
    from app.blueprints.teacher_suivi import teacher_suivi_bp
    app.register_blueprint(teacher_suivi_bp)
    from app.services.suivi import fr_filter
    app.jinja_env.filters['fr'] = fr_filter

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

    # ── Routes racines ─────────────────────────────────────────────────────────
    @app.route('/ping')
    def ping():
        return {"status": "ok", "app": "VoxCorr"}

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # ─ Hooks avant requête ───────────────────────────────────────────────────
    @app.before_request
    def before_request_hooks():
        # Expiration automatique de la session admin après 30 minutes
        unlocked_at = session.get('admin_unlocked_at')
        if unlocked_at:
            try:
                unlocked_dt = datetime.fromisoformat(unlocked_at)
                if datetime.now(timezone.utc) - unlocked_dt > timedelta(minutes=30):
                    session.pop('admin_unlocked', None)
                    session.pop('admin_unlocked_at', None)
            except ValueError:
                # Si le format de date est corrompu, on nettoie la session
                session.pop('admin_unlocked_at', None)
                # Compte suspendu : déconnexion immédiate
        from flask_login import current_user, logout_user
        if current_user.is_authenticated and not getattr(current_user, 'email_verified', True):
            logout_user()

    # ── Context processor pour breadcrumb dynamique ─────────────────────────────
    @app.context_processor
    def inject_breadcrumb():
        from app.utils.breadcrumbs import build_breadcrumb
        from flask import request
        
        def generate_breadcrumb():
            endpoint = request.endpoint
            if not endpoint:
                return []
            return build_breadcrumb(endpoint, dict(request.view_args or {}))
        
        return dict(generate_breadcrumb=generate_breadcrumb, now=datetime.now(timezone.utc))

    return app, socketio