from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort
from app import db
from app.models import Pupil, Correction
from app.services.anonymization import decrypt_name

student_bp = Blueprint('student', __name__, url_prefix='/student')

@student_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        code = request.form.get('access_code', '').strip().upper()
        pupil = Pupil.query.filter_by(access_code=code).first()
        if pupil:
            session['pupil_id'] = pupil.id
            return redirect(url_for('student.dashboard'))
        flash('Code invalide', 'danger')
    return render_template('student/login.html')

@student_bp.route('/dashboard')
def dashboard():
    if 'pupil_id' not in session:
        return redirect(url_for('student.login'))
    pupil = Pupil.query.get(session['pupil_id'])
    corrections = Correction.query.filter_by(student_id=pupil.student_id, status='published').order_by(Correction.created_at.desc()).all()
    return render_template('student/dashboard.html', pupil=pupil, corrections=corrections)

@student_bp.route('/correction/<int:correction_id>')
def view_correction(correction_id):
    if 'pupil_id' not in session:
        return redirect(url_for('student.login'))
    pupil = Pupil.query.get(session['pupil_id'])
    correction = Correction.query.get_or_404(correction_id)
    if correction.student_id != pupil.student_id:
        abort(403)
    first = decrypt_name(correction.student.encrypted_first_name)
    last = decrypt_name(correction.student.encrypted_last_name)
    return render_template('student/correction.html', correction=correction, first=first, last=last)

@student_bp.route('/logout')
def logout():
    session.pop('pupil_id', None)
    return redirect(url_for('student.login'))