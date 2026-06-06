from flask import Blueprint, render_template, redirect, url_for, request, flash, session, abort, jsonify, send_file
from app import db, limiter
from app.models import Pupil, Correction
from app.services.anonymization import decrypt_name
from app.services.tts import generate_tts_audio
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
    corrections = Correction.query.filter_by(student_id=pupil.student_id, status='published').order_by(Correction.created_at.desc()).all()
    return render_template('student/dashboard.html', pupil=pupil, corrections=corrections)

@student_bp.route('/correction/<int:correction_id>')
def view_correction(correction_id):
    if 'pupil_id' not in session:
        return redirect(url_for('student.login'))
    pupil = db.session.get(Pupil, session['pupil_id'])
    if not pupil:
        session.pop('pupil_id', None)
        return redirect(url_for('student.login'))
    correction = db.session.get(Correction, correction_id)
    if not correction or correction.student_id != pupil.student_id:
        abort(403)
    first = decrypt_name(correction.student.encrypted_first_name)
    last = decrypt_name(correction.student.encrypted_last_name)
    # Marquer comme lu (RGPD)
    if not correction.read_at:
        correction.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return render_template('student/correction.html', correction=correction, first=first, last=last)

@student_bp.route('/api/tts/<int:correction_id>')
@limiter.limit("20 per hour")
def tts_correction(correction_id):
    if 'pupil_id' not in session:
        return jsonify({'error': 'Non autorisé'}), 401
    
    pupil = db.session.get(Pupil, session['pupil_id'])
    if not pupil:
        return jsonify({'error': 'Session invalide'}), 401
    
    correction = db.session.get(Correction, correction_id)
    if not correction or correction.student_id != pupil.student_id:
        abort(403)
    
    if not correction.structured_text:
        return jsonify({'error': 'Aucune synthèse'}), 404
    
    audio_bytes = generate_tts_audio(correction.structured_text)
    return send_file(
        io.BytesIO(audio_bytes),
        mimetype='audio/mpeg',
        as_attachment=False,
        download_name=f'correction_{correction_id}.mp3'
    )

@student_bp.route('/logout')
def logout():
    session.pop('pupil_id', None)
    return redirect(url_for('student.login'))