import os
from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEV = os.environ.get('VOXCORR_ENV') == 'dev'
# Mode développement : .env.dev (base SQLite locale). Sinon : .env habituel.
load_dotenv(os.path.join(_ROOT, '.env.dev' if _DEV else '.env'))

class Config:
    # ── Flask ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY non définie dans les variables d'environnement")

    # ── Base de données ────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///voxcorr_dev.db'
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    DEV_MODE = _DEV
    if _DEV and not SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        raise RuntimeError("Mode développement : la base doit être SQLite. "
                           "Vérifiez .env.dev et les variables d'environnement de Windows.")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    if SQLALCHEMY_DATABASE_URI.startswith('postgresql'):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"sslmode": "require"}

    # ── Flask-Login ────────────────────────────────────────────────────────────
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # ── Cloudinary ─────────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # ── Mistral ────────────────────────────────────────────────────────────────
    MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY')

    # ── RGPD — chiffrement noms élèves ─────────────────────────────────────────
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')
    if not ENCRYPTION_KEY:
        raise RuntimeError("ENCRYPTION_KEY non définie dans les variables d'environnement")

    # ── URL publique ───────────────────────────────────────────────────────────
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')

    # ── Upload ─────────────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 Mo max (sécurité)

    # ── Session ────────────────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24  # 24h pour élèves
    SESSION_COOKIE_SECURE = not _DEV  # HTTPS uniquement, sauf en développement local