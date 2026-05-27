import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import Teacher
import hashlib
import hmac
import os

def hash_password(password):
    return generate_password_hash(password)

def verify_password(password, hashed):
    return check_password_hash(hashed, password)

def generate_token(teacher_id):
    payload = {
        'exp': datetime.now(timezone.utc) + timedelta(days=7), # Expire dans 7 jours
        'iat': datetime.now(timezone.utc),
        'sub': teacher_id
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

# Décorateur pour protéger nos futures routes
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Le token doit être envoyé dans le header "Authorization: Bearer <token>"
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token manquant !'}), 401
        
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            current_teacher = Teacher.query.get(data['sub'])
            if not current_teacher:
                raise Exception("Professeur introuvable")
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expiré !'}), 401
        except Exception as e:
            return jsonify({'message': 'Token invalide !'}), 401
            
        return f(current_teacher, *args, **kwargs)
    return decorated

def hash_ip(ip: str) -> str:
    """
    Retourne un hash HMAC-SHA256 de l'IP, salé avec SECRET_KEY.
    RGPD : l'IP hashée n'est pas directement identifiable sans la clé.
    Résistant aux attaques par table arc-en-ciel sur les IPs connues.
    """
    secret = os.environ.get("SECRET_KEY", "fallback-dev-secret")
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()