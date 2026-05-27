import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Flask ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-CHANGE-IN-PRODUCTION'

    # ── Base de données (Neon / SQLite en dev) ─────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///voxcorr_dev.db'
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,        # vérifie la connexion avant chaque requête
        "pool_recycle": 300,          # renouvelle les connexions toutes les 5 min
    }

    # ── Flask-Login ────────────────────────────────────────────────────────────
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7   # 7 jours en secondes
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = 'Lax'

    # ── Cloudinary ─────────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY    = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

    # ── Mistral ────────────────────────────────────────────────────────────────
    MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY')

    # ── RGPD — chiffrement noms élèves ─────────────────────────────────────────
    # Génère avec : python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

    # ── URL publique (pour les QR codes) ──────────────────────────────────────
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')

    # ── Upload ─────────────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024   # 50 Mo max
