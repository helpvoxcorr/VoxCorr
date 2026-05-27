from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Teacher
import re

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


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
            login_user(teacher, remember=remember)
            # Redirige vers la page demandée avant le login si elle existe
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

        if Teacher.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'warning')
            return render_template('auth/register.html')

        password = request.form.get('password', '')
        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{10,}$'
        if not re.match(pattern, password):
            flash('Mot de passe : 10 caractères minimum, majuscule, minuscule, chiffre et caractère spécial.', 'warning')
            return render_template('auth/register.html')
        
        teacher = Teacher(
            email      = email,
            first_name = request.form.get('first_name', '').strip(),
            last_name  = request.form.get('last_name',  '').strip(),
            school     = request.form.get('school',     '').strip(),
        )
        teacher.set_password(request.form.get('password', ''))

        db.session.add(teacher)
        db.session.commit()

        login_user(teacher)
        flash(f'Bienvenue, {teacher.first_name} ! Votre espace est prêt.', 'success')
        return redirect(url_for('teacher.dashboard'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
