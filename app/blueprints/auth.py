from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import Teacher
from app.services.email import send_verification_email
from urllib.parse import urlparse, urljoin
from werkzeug.security import check_password_hash, generate_password_hash
import re

_DUMMY_HASH = generate_password_hash("dummy")

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Regex corrigées (lookaheads complets)
PASSWORD_PATTERN = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{10,}$'
EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

def is_safe_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 50 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('teacher_crud.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        teacher = Teacher.query.filter_by(email=email).first()

        if teacher:
            password_valid = teacher.check_password(password)
        else:
            check_password_hash(_DUMMY_HASH, password)
            password_valid = False

        if teacher and password_valid:
            if teacher.email_verified:
                login_user(teacher, remember=remember)
                session.permanent = True
                next_page = request.args.get('next')
                if not is_safe_url(next_page):
                    next_page = None
                return redirect(next_page or url_for('teacher_crud.dashboard'))

            flash("Votre compte n'est pas encore activé. Vérifiez votre boîte mail.", "warning")
            return render_template('auth/login.html')

        flash('Email ou mot de passe incorrect.', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('teacher_crud.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not re.match(EMAIL_PATTERN, email):
            flash('Adresse email invalide.', 'warning')
            return render_template('auth/register.html')

        if Teacher.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'warning')
            return render_template('auth/register.html')

        password = request.form.get('password', '')
        if not re.match(PASSWORD_PATTERN, password):
            flash('Mot de passe : 10 caractères min., majuscule, minuscule, chiffre et caractère spécial.', 'warning')
            return render_template('auth/register.html')

        confirm = request.form.get('confirm_password', '')
        if password != confirm:
            flash('Les mots de passe ne correspondent pas.', 'warning')
            return render_template('auth/register.html')

        teacher = Teacher(
            email=email,
            first_name=request.form.get('first_name', '').strip(),
            last_name=request.form.get('last_name', '').strip(),
            school=request.form.get('school', '').strip(),
        )
        teacher.set_password(password)
        token = teacher.generate_verification_token()

        db.session.add(teacher)
        db.session.commit()

        sent = send_verification_email(
            to_email=email,
            first_name=teacher.first_name or 'Enseignant',
            token=token,
        )

        if sent:
            flash(f'Compte créé ! Email de confirmation envoyé à {email}.', 'success')
            return redirect(url_for('auth.login'))

        db.session.delete(teacher)
        db.session.commit()
        flash("Impossible d'envoyer l'email de confirmation. Réessayez plus tard.", "danger")
        return render_template('auth/register.html')

    return render_template('auth/register.html')

@auth_bp.route('/verify/<token>')
def verify_email(token):
    teacher = Teacher.query.filter_by(verification_token=token).first()
    if not teacher:
        flash('Lien de vérification invalide ou expiré.', 'danger')
        return redirect(url_for('auth.login'))

    teacher.email_verified = True
    teacher.verification_token = None
    db.session.commit()

    login_user(teacher)
    session.permanent = True
    flash(f'Email confirmé ! Bienvenue, {teacher.first_name}.', 'success')
    return redirect(url_for('teacher_crud.dashboard'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))