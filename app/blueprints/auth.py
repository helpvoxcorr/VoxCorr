from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Teacher
from app.services.email import send_verification_email
import re

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

PASSWORD_PATTERN = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{10,}$'
EMAIL_PATTERN    = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('teacher.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        teacher = Teacher.query.filter_by(email=email).first()
        if teacher and teacher.check_password(password):
            if not teacher.email_verified:
                flash('Veuillez confirmer votre adresse email avant de vous connecter.', 'warning')
                return render_template('auth/login.html')
            login_user(teacher, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('teacher.dashboard'))

        flash('Email ou mot de passe incorrect.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('teacher.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Validation email
        if not re.match(EMAIL_PATTERN, email):
            flash('Adresse email invalide.', 'warning')
            return render_template('auth/register.html')

        if Teacher.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'warning')
            return render_template('auth/register.html')

        # Validation mot de passe
        password = request.form.get('password', '')
        if not re.match(PASSWORD_PATTERN, password):
            flash('Mot de passe : 10 caractères min., majuscule, minuscule, chiffre et caractère spécial.', 'warning')
            return render_template('auth/register.html')

        # Confirmation mot de passe
        confirm = request.form.get('confirm_password', '')
        if password != confirm:
            flash('Les mots de passe ne correspondent pas.', 'warning')
            return render_template('auth/register.html')

        # Création du compte
        teacher = Teacher(
            email      = email,
            first_name = request.form.get('first_name', '').strip(),
            last_name  = request.form.get('last_name',  '').strip(),
            school     = request.form.get('school',     '').strip(),
        )
        teacher.set_password(password)
        token = teacher.generate_verification_token()

        db.session.add(teacher)
        db.session.commit()

        # Envoi email de vérification
        sent = send_verification_email(
            to_email   = email,
            first_name = teacher.first_name or 'Enseignant',
            token      = token,
        )

        if sent:
            flash(f'Compte créé ! Un email de confirmation a été envoyé à {email}.', 'success')
        else:
            # En dev ou si SendGrid échoue : on active directement
            teacher.email_verified = True
            db.session.commit()
            login_user(teacher)
            flash(f'Bienvenue, {teacher.first_name} ! Votre espace est prêt.', 'success')
            return redirect(url_for('teacher.dashboard'))

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/verify/<token>')
def verify_email(token):
    teacher = Teacher.query.filter_by(verification_token=token).first()
    if not teacher:
        flash('Lien de vérification invalide ou expiré.', 'danger')
        return redirect(url_for('auth.login'))

    teacher.email_verified     = True
    teacher.verification_token = None
    db.session.commit()

    login_user(teacher)
    flash(f'Email confirmé ! Bienvenue, {teacher.first_name} 🎉', 'success')
    return redirect(url_for('teacher.dashboard'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))