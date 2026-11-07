import os, hmac
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import Teacher
from urllib.parse import urlparse, urljoin
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import re

_DUMMY_HASH = generate_password_hash("dummy")

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Regex corrigées (lookaheads complets)
PASSWORD_PATTERN = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{10,}$'
EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
def _norm_code(value):
    """Majuscules, sans espace ni tiret : « k7p2-qx » devient « K7P2QX »."""
    return re.sub(r'[^A-Z0-9]', '', (value or '').upper())


def _invite_codes():
    """INVITE_CODES="marie:K7P2QX,paul:9TD4WM" donne {'K7P2QX': 'marie', '9TD4WM': 'paul'}."""
    codes = {}
    for item in os.environ.get('INVITE_CODES', '').split(','):
        item = item.strip()
        if not item:
            continue
        name, sep, code = item.partition(':')
        if not sep:
            name, code = 'invité', name
        code = _norm_code(code)
        if code:
            codes[code] = name.strip() or 'invité'
    return codes


def _check_invite(value):
    """Nom de l'invité si le code est valide, sinon None."""
    given = _norm_code(value)
    if not given:
        return None
    found = None
    for code, name in _invite_codes().items():
        if hmac.compare_digest(code, given):
            found = name
    return found

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

            flash("Ce compte n'est pas actif. Contactez l'administrateur.", "warning")
            return render_template('auth/login.html')

        flash('Email ou mot de passe incorrect.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('teacher_crud.dashboard'))
    if not _invite_codes():
        flash("Les comptes sont créés par l'administrateur. Demandez-lui un accès.", 'info')
        return redirect(url_for('auth.login'))

    def page():
        prefill = request.form.get('invite_code') or request.args.get('code', '')
        return render_template(
            'auth/register.html',
            form=request.form,
            invite_prefill=prefill
        )

    if request.method == 'POST':

        # Vérification du code d'invitation
        invited_as = _check_invite(request.form.get('invite_code'))

        if not invited_as:
            current_app.logger.warning(
                "Inscription refusée : code d'invitation invalide (IP %s)",
                request.remote_addr
            )
            flash(
                "Code d'invitation invalide. Demandez-le à l'administrateur.",
                'danger'
            )
            return page()

        # Vérification de l'email
        email = request.form.get('email', '').strip().lower()

        if not re.match(EMAIL_PATTERN, email):
            flash('Adresse email invalide.', 'warning')
            return page()

        if Teacher.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'warning')
            return page()

        # Vérification du mot de passe
        password = request.form.get('password', '')

        if not re.match(PASSWORD_PATTERN, password):
            flash(
                'Mot de passe : 10 caractères min., majuscule, minuscule, chiffre et caractère spécial.',
                'warning'
            )
            return page()

        # Confirmation du mot de passe
        confirm = request.form.get('confirm_password', '')

        if password != confirm:
            flash('Les mots de passe ne correspondent pas.', 'warning')
            return page()

        # Création du compte
        teacher = Teacher(
            email=email,
            first_name=request.form.get('first_name', '').strip(),
            last_name=request.form.get('last_name', '').strip(),
            school=request.form.get('school', '').strip(),
        )

        teacher.set_password(password)
        teacher.email_verified = True

        db.session.add(teacher)
        db.session.commit()

        current_app.logger.info(
            'Compte créé : %s (invité : %s)',
            email,
            invited_as
        )

        flash('Compte créé. Vous pouvez vous connecter.', 'success')

        return redirect(url_for('auth.login'))

    # Affichage du formulaire lors d'une requête GET
    return page()

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='vc-password-reset')


def make_reset_token(teacher):
    """Lien à usage unique : il contient une empreinte de l'ancien mot de passe,
    donc il cesse de marcher dès que le mot de passe change."""
    return _reset_serializer().dumps({'id': teacher.id, 'f': (teacher.password_hash or '')[-16:]})


def _teacher_from_reset_token(token, max_age=48 * 3600):
    try:
        data = _reset_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    t = db.session.get(Teacher, data.get('id'))
    if not t or not hmac.compare_digest((t.password_hash or '')[-16:], data.get('f', '')):
        return None
    return t


@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token):
    teacher = _teacher_from_reset_token(token)
    if not teacher:
        flash("Ce lien est invalide, déjà utilisé ou expiré. Demandez-en un nouveau à l'administrateur.", 'danger')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if not re.match(PASSWORD_PATTERN, pw):
            flash('Mot de passe : 10 caractères min., majuscule, minuscule, chiffre et caractère spécial.', 'warning')
        elif pw != request.form.get('confirm_password', ''):
            flash('Les mots de passe ne correspondent pas.', 'warning')
        else:
            teacher.set_password(pw)
            teacher.email_verified = True
            db.session.commit()
            current_app.logger.info('Mot de passe réinitialisé : %s', teacher.email)
            flash('Mot de passe modifié. Vous pouvez vous connecter.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/reset.html', first_name=teacher.first_name)


@auth_bp.route('/password', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def change_password():
    if request.method == 'POST':
        new = request.form.get('new_password', '')
        if not current_user.check_password(request.form.get('current', '')):
            flash('Mot de passe actuel incorrect.', 'danger')
        elif not re.match(PASSWORD_PATTERN, new):
            flash('Mot de passe : 10 caractères min., majuscule, minuscule, chiffre et caractère spécial.', 'warning')
        elif new != request.form.get('confirm_password', ''):
            flash('Les mots de passe ne correspondent pas.', 'warning')
        else:
            current_user.set_password(new)
            db.session.commit()
            flash('Mot de passe modifié.', 'success')
            return redirect(url_for('teacher_crud.dashboard'))
    return render_template('auth/change_password.html')