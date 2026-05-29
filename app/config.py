import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Flask ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-CHANGE-IN-PRODUCTION'

    # ── Base de données ────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///voxcorr_dev.db'
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "connect_args": {"sslmode": "require"},
    }

    # ── Flask-Login ────────────────────────────────────────────────────────────
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = 'Lax'

    # ── Cloudinary ─────────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY    = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # ── Mistral ────────────────────────────────────────────────────────────────
    MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY')

    # ── RGPD — chiffrement noms élèves ─────────────────────────────────────────
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

    # ── URL publique ───────────────────────────────────────────────────────────
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')

    # ── Upload ─────────────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    # ── SendGrid ───────────────────────────────────────────────────────────────
    SENDGRID_API_KEY    = os.environ.get('SENDGRID_API_KEY')
    SENDGRID_FROM_EMAIL = os.environ.get('SENDGRID_FROM_EMAIL', 'help.voxcorr@gmail.com')
    SENDGRID_FROM_NAME  = os.environ.get('SENDGRID_FROM_NAME',  'VoxCorr Team')