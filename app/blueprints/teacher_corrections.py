from flask import (Blueprint, render_template, redirect, url_for, request, jsonify, flash, send_file, current_app, abort)
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.models import (Assignment, Student, Correction, QuestionScore, Question, Competence)
from app.services.anonymization import decrypt_name
from app.services.ai import synthesize_with_mistral, synthesize_appreciation
from app.services.storage import upload_audio
from app.services.qrcode import make_qr, qr_png_bytes
from app.services.background import run_in_background
from app.services.tts import generate_tts_audio
import io
from datetime import datetime, timezone

teacher_corr_bp = Blueprint('teacher_corr', __name__, url_prefix='/teacher')

@teacher_corr_bp.route('/assignments/<int:assignment_id>/corrections')
@login_required
def assignment_corrections(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a: abort(404)
    if a.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    students = Student.query.filter_by(classroom_id=a.classroom_id).order_by(Student.student_number).all()
    for s in students:
        s.correction = Correction.query.filter_by(student_id=s.id, assignment_id=assignment_id).first()
        try: s.display_last = decrypt_name(s.encrypted_last_name); s.display_first = decrypt_name(s.encrypted_first_name)
        except Exception: s.display_last = s.display_first = '—'
    return render_template('teacher/assignment_corrections.html', assignment=a, students=students)

@teacher_corr_bp.route('/record/<int:student_id>/<int:assignment_id>')
@login_required
def record(student_id, assignment_id):
    student = db.session.get(Student, student_id)
    if not student: abort(404)
    try: student_first = decrypt_name(student.encrypted_first_name); student_last = decrypt_name(student.encrypted_last_name)
    except Exception: student_first = student_last = '—'
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment: abort(404)
    if assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    student = db.session.get(Student, student_id)
    if not student or student.classroom_id != assignment.classroom_id: return jsonify({'error': 'Élève non trouvé dans cette classe'}), 404
    corr = Correction.query.filter_by(student_id=student_id, assignment_id=assignment_id).first()
    all_students = Student.query.filter_by(classroom_id=assignment.classroom_id).all()
    def _sort_key(s):
        try: return decrypt_name(s.encrypted_last_name).lower()
        except Exception: return s.alias.lower()
    all_students.sort(key=_sort_key)
    ids = [s.id for s in all_students]
    try: idx = ids.index(student_id)
    except ValueError: idx = 0
    prev_id = ids[idx - 1] if idx > 0 else None; next_id = ids[idx + 1] if idx < len(ids) - 1 else None
    def _has_correction(sid):
        if sid is None: return False
        return Correction.query.filter_by(student_id=sid, assignment_id=assignment_id).first() is not None
    return render_template('teacher/record.html', student=student, assignment=assignment, questions=assignment.questions, existing=corr, prev_student_id=prev_id, next_student_id=next_id, has_prev_correction=_has_correction(prev_id), has_next_correction=_has_correction(next_id), student_index=idx + 1, student_first=student_first, student_last=student_last, student_total=len(ids))

@teacher_corr_bp.route('/assignments/<int:assignment_id>/print')
@login_required
def print_corrections(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a: abort(404)
    if a.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    students = Student.query.filter_by(classroom_id=a.classroom_id).order_by(Student.student_number).all()
    cards = []
    for s in students:
        try: first = decrypt_name(s.encrypted_first_name); last = decrypt_name(s.encrypted_last_name)
        except Exception: first = last = '—'
        corr = Correction.query.filter_by(student_id=s.id, assignment_id=assignment_id, status='published').first()
        if not corr: continue
        qr = make_qr(corr.public_token)
        cards.append({'alias': s.alias, 'first_name': first, 'last_name': last, 'score': corr.total_score, 'text': corr.structured_text or ' ', 'qr_b64': qr['png_b64'], 'qr_url': qr['url']})
    cards.sort(key=lambda c: c['last_name'].lower())
    return render_template('teacher/print_corrections.html', assignment=a, cards=cards)

@teacher_corr_bp.route('/correction/<int:correction_id>')
@login_required
def correction_detail(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    student = corr.student
    try: student.display_first = decrypt_name(student.encrypted_first_name); student.display_last = decrypt_name(student.encrypted_last_name)
    except Exception: student.display_first = student.display_last = '—'
    qr = make_qr(corr.public_token) if corr.status == 'published' else {}
    return render_template('teacher/correction_detail.html', correction=corr, student=student, qr_b64=qr.get('png_b64', ''), qr_url=qr.get('url', ''))

@teacher_corr_bp.route('/correction/<int:correction_id>/preview')
@login_required
def preview_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    if corr.status == 'published': return redirect(url_for('public.student_view', token=corr.public_token))
    if corr.status not in ('draft',): flash(f"Aperçu non disponible — correction en statut « {corr.status} ».", "warning"); return redirect(url_for('teacher_corr.correction_detail', correction_id=correction_id))
    scores_detail = [{'label': qs.question.label, 'score': qs.score, 'max': qs.question.max_points, 'competence': qs.question.competence} for qs in corr.scores]
    return render_template('public/student.html', correction=corr, scores=scores_detail, teacher=corr.assignment.classroom.teacher, preview_mode=True)

@teacher_corr_bp.route('/api/correction/save', methods=['POST'])
@login_required
@limiter.limit("10 per minute; 50 per hour")
def save_correction():
    data = request.get_json(); student_id = data['student_id']; assignment_id = data['assignment_id']; transcript = data.get('transcript', ''); scores_data = data.get('scores', [])
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment: abort(404)
    if assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    student = db.session.get(Student, student_id)
    if not student or student.classroom_id != assignment.classroom_id: return jsonify({'error': 'Élève invalide pour cette classe'}), 404
    corr = Correction.query.filter_by(student_id=student_id, assignment_id=assignment_id).first()
    if not corr: corr = Correction(student_id=student_id, assignment_id=assignment_id); db.session.add(corr)
    corr.raw_transcript = transcript; corr.status = 'processing'; db.session.flush(); corr_id = corr.id
    q_max_by_id = {q.id: q.max_points for q in assignment.questions}
    QuestionScore.query.filter_by(correction_id=corr_id).delete()
    for s in scores_data:
        max_pts = q_max_by_id.get(s['question_id']); score = min(float(s['score']), max_pts) if max_pts is not None else float(s['score'])
        db.session.add(QuestionScore(correction_id=corr_id, question_id=s['question_id'], score=score))
    corr.compute_total(); db.session.commit()
    q_labels = [q.label for q in assignment.questions]; q_ids = [q.id for q in assignment.questions]; q_max = [q.max_points for q in assignment.questions]
    app = current_app._get_current_object()
    def _synthesize():
        with app.app_context():
            c = db.session.get(Correction, corr_id)
            if not c: return
            try:
                result = synthesize_with_mistral(c.raw_transcript, q_labels, q_max); c.structured_text = result.get('formatted_text', c.raw_transcript)
                existing_scores = {qs.question_id: qs for qs in c.scores}; grades = result.get('grades', [])
                for ai_score in grades:
                    idx = ai_score.get('question_index')
                    if idx is None: idx = grades.index(ai_score)
                    if idx is None or idx >= len(q_ids): continue
                    qid = q_ids[idx]
                    if qid in existing_scores: continue
                    raw_score = float(ai_score['score']); safe_score = min(raw_score, q_max[idx]); advice_text = ai_score.get('advice', '')
                    qs = QuestionScore(correction_id=corr_id, question_id=qid, score=safe_score, advice=advice_text); db.session.add(qs); existing_scores[qid] = qs
                db.session.flush(); c.compute_total(); c.status = 'draft'; db.session.commit()
            except Exception as e: db.session.rollback(); c.status = 'draft'; db.session.commit(); print(f"[Mistral] Erreur dans _synthesize: {e}")
    import threading; threading.Thread(target=_synthesize, daemon=True).start()
    return jsonify({'ok': True, 'correction_id': corr_id})

@teacher_corr_bp.route('/api/correction/<int:correction_id>/status')
@login_required
def correction_status(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 404
    return jsonify({'status': corr.status, 'structured_text': corr.structured_text or '', 'total_score': corr.total_score})

@teacher_corr_bp.route('/api/correction/<int:correction_id>/scores')
@login_required
def correction_scores(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return jsonify([])
    return jsonify([{'question_id': s.question_id, 'score': s.score} for s in corr.scores])

@teacher_corr_bp.route('/api/correction/<int:correction_id>/audio', methods=['POST'])
@login_required
def upload_audio_route(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    audio_file = request.files.get('audio')
    if not audio_file: return jsonify({'error': 'Fichier manquant'}), 400
    ALLOWED_EXTENSIONS = {'webm', 'mp3', 'wav', 'm4a', 'ogg'}
    extension = audio_file.filename.rsplit('.', 1)[-1].lower() if '.' in audio_file.filename else ''
    if extension not in ALLOWED_EXTENSIONS: return jsonify({'error': f'Extension .{extension} non autorisée.'}), 400
    try:
        result = upload_audio(audio_file.read(), public_id=f'corr_{corr.public_token}', teacher_id=current_user.id)
        corr.audio_url = result['url']; corr.audio_duration = result.get('duration'); db.session.commit()
        return jsonify({'ok': True, 'audio_url': corr.audio_url})
    except Exception as e: return jsonify({'error': str(e)}), 500

@teacher_corr_bp.route('/api/correction/<int:correction_id>/publish', methods=['POST'])
@login_required
def publish_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    corr.publish(); db.session.commit(); qr = make_qr(corr.public_token)
    return jsonify({'ok': True, 'qr': qr['png_b64'], 'url': qr['url']})

@teacher_corr_bp.route('/correction/<int:correction_id>/qr.png')
@login_required
def download_qr(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return 'Non autorisé', 403
    classroom_name = corr.assignment.classroom.name.replace(' ', ''); assignment_name = corr.assignment.title.replace(' ', ''); alias = corr.student.alias.replace('-', '')
    filename = f'{classroom_name}{assignment_name}_{alias}.png'
    return send_file(io.BytesIO(qr_png_bytes(corr.public_token)), mimetype='image/png', as_attachment=True, download_name=filename)

@teacher_corr_bp.route('/api/correction/<int:correction_id>/delete', methods=['POST'])
@login_required
def delete_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    data = request.get_json(silent=True) or {}
    if not current_user.check_password(data.get('password', '')): return jsonify({'error': 'Mot de passe incorrect'}), 403
    assignment_id = corr.assignment_id; db.session.delete(corr); db.session.commit()
    return jsonify({'ok': True, 'assignment_id': assignment_id})

@teacher_corr_bp.route('/api/corrections/delete-bulk', methods=['POST'])
@login_required
def delete_corrections_bulk():
    data = request.get_json(silent=True) or {}
    if not current_user.check_password(data.get('password', '')): return jsonify({'error': 'Mot de passe incorrect'}), 403
    ids = data.get('ids', [])
    if len(ids) > 100: return jsonify({'error': 'Trop de corrections sélectionnées (max 100)'}), 400
    if not ids: return jsonify({'error': 'Aucune correction sélectionnée'}), 400
    deleted = 0
    for cid in ids:
        corr = db.session.get(Correction, cid)
        if corr and corr.assignment.classroom.teacher_id == current_user.id: db.session.delete(corr); deleted += 1
    db.session.commit(); return jsonify({'ok': True, 'deleted': deleted})

@teacher_corr_bp.route('/api/correction/<int:correction_id>/resynthesize', methods=['POST'])
@login_required
@limiter.limit("5 per minute; 20 per hour")
def resynthesize_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    if corr.status == 'published': return jsonify({'error': 'Impossible de modifier une correction publiée'}), 400
    if not corr.raw_transcript: return jsonify({'error': 'Aucune transcription disponible.'}), 400
    questions = corr.assignment.questions; q_labels = [q.label for q in questions]; q_max_points = [q.max_points for q in questions]
    app_ctx = current_app._get_current_object()
    def _do_resynthesize():
        with app_ctx.app_context():
            try:
                result = synthesize_with_mistral(corr.raw_transcript, q_labels, q_max_points); corr.structured_text = result.get('formatted_text', corr.raw_transcript); corr.status = 'draft'; db.session.commit()
            except Exception as e: app_ctx.logger.error(f'Resynthesize error corr {correction_id}: {e}')
    run_in_background(_do_resynthesize); return jsonify({'ok': True})

@teacher_corr_bp.route('/assignments/<int:assignment_id>/appreciation', methods=['POST'])
@login_required
def save_appreciation(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a: abort(404)
    if a.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    a.class_appreciation = request.get_json().get('text', '').strip() or None; db.session.commit(); return jsonify({'ok': True})

@teacher_corr_bp.route('/assignments/<int:assignment_id>/appreciation/synthesize', methods=['POST'])
@login_required
@limiter.limit("5 per minute; 20 per hour")
def synthesize_appreciation_route(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a: abort(404)
    if a.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    raw = request.get_json().get('text', '').strip()
    if not raw: return jsonify({'error': 'Texte vide'}), 400
    result = synthesize_appreciation(raw); return jsonify({'ok': True, 'text': result})

@teacher_corr_bp.route('/correction/<int:correction_id>/pdf')
@login_required
def correction_pdf(correction_id):
    from weasyprint import HTML
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    student = corr.student
    scores_detail = [{'label': qs.question.label, 'score': qs.score, 'max': qs.question.max_points, 'competence': qs.question.competence} for qs in corr.scores]
    qr_url = f"{current_app.config['APP_BASE_URL']}/c/{corr.public_token}"; qr_data = make_qr(corr.public_token) if corr.status == 'published' else None; qr_b64 = qr_data['png_b64'] if qr_data else None
    html_str = render_template('teacher/correction_pdf.html', correction=corr, student=student, scores=scores_detail, qr_b64=qr_b64, qr_url=qr_url if corr.status == 'published' else None, teacher=corr.assignment.classroom.teacher, now=datetime.now(timezone.utc))
    try: pdf = HTML(string=html_str, base_url=request.host_url).write_pdf()
    except Exception: flash("Erreur lors de la génération du PDF.", "danger"); return redirect(url_for('teacher_corr.correction_detail', correction_id=correction_id))
    return current_app.response_class(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename="correction-{student.alias}-{corr.assignment.title}.pdf"'})

@teacher_corr_bp.route('/api/tts/<int:correction_id>')
@login_required
def tts_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr: abort(404)
    if corr.assignment.classroom.teacher_id != current_user.id: abort(403)
    if not corr.structured_text: return jsonify({'error': 'Aucune synthèse disponible'}), 404
    audio_bytes = generate_tts_audio(corr.structured_text)
    return send_file(io.BytesIO(audio_bytes), mimetype='audio/mpeg', as_attachment=False, download_name=f'correction_{correction_id}.mp3')

@teacher_corr_bp.route('/competences')
@login_required
def list_competences():
    competences = Competence.query.filter_by(teacher_id=current_user.id).order_by(Competence.name).all()
    return render_template('teacher/competences.html', competences=competences)

@teacher_corr_bp.route('/competences/<int:comp_id>/delete', methods=['POST'])
@login_required
def delete_competence(comp_id):
    comp = Competence.query.get_or_404(comp_id)
    if comp.teacher_id != current_user.id: abort(403)
    db.session.delete(comp); db.session.commit(); flash('Compétence supprimée.', 'success'); return redirect(url_for('teacher_corr.list_competences'))