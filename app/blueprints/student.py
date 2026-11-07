from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort, jsonify, send_file
from app.extensions import db, limiter
from app.models import Pupil, Correction
from app.services.anonymization import decrypt_name
from datetime import datetime, timezone
import io

student_bp = Blueprint('student', __name__, url_prefix='/student')

@student_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 100 per hour")
def login():
    if request.method == 'POST':
        code = request.form.get('access_code', '').strip().upper()
        pupil = Pupil.query.filter_by(access_code=code).first()
        if pupil:
            session['pupil_id'] = pupil.id
            session.permanent = True
            return redirect(url_for('student.dashboard'))
        flash('Code invalide', 'danger')
    return render_template('student/login.html')

@student_bp.route('/dashboard')
def dashboard():
    if 'pupil_id' not in session:
        return redirect(url_for('student.login'))
    pupil = db.session.get(Pupil, session['pupil_id'])
    if not pupil:
        session.pop('pupil_id', None)
        return redirect(url_for('student.login'))
    corrections = Correction.query.filter_by(
        student_id=pupil.student_id, status='published'
    ).order_by(Correction.created_at.desc()).all()
    try:
        first_name = decrypt_name(pupil.student.encrypted_first_name)
    except Exception:
        first_name = pupil.student.alias
    return render_template('student/dashboard.html', pupil=pupil,
                           corrections=corrections, first_name=first_name)


@student_bp.route('/correction/<int:correction_id>')
def view_correction(correction_id):
    if 'pupil_id' not in session:
        return redirect(url_for('student.login'))
    pupil = db.session.get(Pupil, session['pupil_id'])
    if not pupil:
        session.pop('pupil_id', None)
        return redirect(url_for('student.login'))
    correction = db.session.get(Correction, correction_id)
    if not correction or correction.student_id != pupil.student_id or correction.status != 'published':
        abort(404)
    return redirect(url_for('public.student_view', token=correction.public_token))

@student_bp.route('/logout')
def logout():
    session.pop('pupil_id', None)
    return redirect(url_for('student.login'))