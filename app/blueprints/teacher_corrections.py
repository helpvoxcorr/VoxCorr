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
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        abort(404)
    if assignment.classroom.teacher_id != current_user.id:
        abort(403)
    student = db.session.get(Student, student_id)
    if not student or student.classroom_id != assignment.classroom_id:
        abort(404)

    def _label(s):
        try:
            return f"{decrypt_name(s.encrypted_last_name)} {decrypt_name(s.encrypted_first_name)}"
        except Exception:
            return s.alias

    student_label = _label(student)
    try:
        student_first = decrypt_name(student.encrypted_first_name)
        student_last = decrypt_name(student.encrypted_last_name)
    except Exception:
        student_first = student_last = '—'

    corr = Correction.query.filter_by(student_id=student_id, assignment_id=assignment_id).first()
    all_students = Student.query.filter_by(classroom_id=assignment.classroom_id).all()
    all_students.sort(key=lambda s: _label(s).lower())
    by_id = {s.id: s for s in all_students}
    ids = [s.id for s in all_students]
    idx = ids.index(student_id) if student_id in ids else 0
    prev_id = ids[idx - 1] if idx > 0 else None
    next_id = ids[idx + 1] if idx < len(ids) - 1 else None

    done_ids = {r[0] for r in db.session.query(Correction.student_id).filter_by(assignment_id=assignment_id).all()}
    todo = [i for i in ids[idx + 1:] if i not in done_ids] or [i for i in ids if i not in done_ids and i != student_id]
    next_todo_id = todo[0] if todo else None

    return render_template(
        'teacher/record.html', student=student, assignment=assignment,
        questions=assignment.questions, existing=corr,
        prev_student_id=prev_id, next_student_id=next_id,
        prev_name=_label(by_id[prev_id]) if prev_id else '',
        next_name=_label(by_id[next_id]) if next_id else '',
        next_todo_id=next_todo_id,
        next_todo_name=_label(by_id[next_todo_id]) if next_todo_id else '',
        student_index=idx + 1, student_total=len(ids),
        student_first=student_first, student_last=student_last)

def _make_card(corr, with_qr=True):
    """Données d'un coupon imprimable : nom, notes, synthèse, QR code."""
    s = corr.student
    try:
        first = decrypt_name(s.encrypted_first_name)
        last = decrypt_name(s.encrypted_last_name)
    except Exception:
        first = last = '—'
    scores = [{'label': qs.question.label, 'score': qs.score,
               'max': qs.question.max_points, 'advice': qs.advice or ''}
              for qs in sorted(corr.scores, key=lambda x: (x.question.order or 0, x.question_id))]
    qr = make_qr(corr.public_token) if with_qr else None
    return {'alias': s.alias, 'first_name': first, 'last_name': last, 'score': corr.total_score,
            'text': corr.structured_text or '', 'scores': scores,
            'qr_b64': qr['png_b64'] if qr else None, 'qr_url': qr['url'] if qr else None}


@teacher_corr_bp.route('/assignments/<int:assignment_id>/print')
@login_required
def print_corrections(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
    if a.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher_crud.dashboard'))
    cards = []
    for corr in Correction.query.filter_by(assignment_id=assignment_id, status='published').all():
        cards.append(_make_card(corr))
    cards.sort(key=lambda c: (c['last_name'].lower(), c['first_name'].lower()))
    return render_template('teacher/print_corrections.html', assignment=a, cards=cards,
                           back_url=url_for('teacher_corr.assignment_corrections', assignment_id=a.id),
                           back_label='Retour au devoir')

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
    scores_detail = [{'label': qs.question.label, 'score': qs.score, 'max': qs.question.max_points, 'competence': qs.question.competence.name if qs.question.competence else None,} for qs in corr.scores]
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
            transcript = c.raw_transcript
            db.session.commit()
            db.session.remove()  # libère la connexion avant l'appel IA
            try:
                result = synthesize_with_mistral(transcript, q_labels, q_max)
                c = db.session.get(Correction, corr_id)  # connexion fraîche
                c.structured_text = result.get('formatted_text') or transcript
                existing_scores = {qs.question_id: qs for qs in c.scores}
                grades = result.get('grades', [])
                for pos, ai_score in enumerate(grades):
                    idx = ai_score.get('question_index')
                    if idx is None:
                        idx = pos
                    if idx >= len(q_ids):
                        continue
                    qid = q_ids[idx]
                    safe_score = min(float(ai_score['score']), q_max[idx])
                    advice_text = ai_score.get('advice', '')
                    if qid in existing_scores:
                        qs = existing_scores[qid]
                        if not qs.score:
                            qs.score = safe_score
                        qs.advice = advice_text
                    else:
                        qs = QuestionScore(correction_id=corr_id, question_id=qid, score=safe_score, advice=advice_text)
                        db.session.add(qs)
                        existing_scores[qid] = qs
                db.session.flush(); c.compute_total(); c.status = 'draft'; db.session.commit()
            except Exception as e:
                db.session.rollback()
                c = db.session.get(Correction, corr_id)
                if c:
                    c.status = 'draft'; db.session.commit()
                print(f"[Mistral] Erreur dans _synthesize: {e}", flush=True)
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

def _apply_ai_grades(c, result, q_ids, q_max):
    """Enregistre les notes/conseils extraits par l'IA (sans écraser une note déjà saisie)."""
    existing = {qs.question_id: qs for qs in c.scores}
    for pos, g in enumerate(result.get('grades', [])):
        idx = g.get('question_index')
        if idx is None:
            idx = pos
        if idx >= len(q_ids):
            continue
        try:
            raw = float(g['score'])
        except (KeyError, TypeError, ValueError):
            continue
        qid = q_ids[idx]
        safe = min(raw, q_max[idx])
        advice = g.get('advice', '')
        if qid in existing:
            qs = existing[qid]
            if not qs.score:
                qs.score = safe
            qs.advice = advice
        else:
            qs = QuestionScore(correction_id=c.id, question_id=qid, score=safe, advice=advice)
            db.session.add(qs)
            existing[qid] = qs
    db.session.flush()
    c.compute_total()

@teacher_corr_bp.route('/assignments/<int:assignment_id>/publish-all', methods=['POST'])
@login_required
def publish_all(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
    if a.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    drafts = Correction.query.filter_by(assignment_id=assignment_id, status='draft').all()
    published = skipped = 0
    for c in drafts:
        # Une synthèse ratée (IA en panne) ne doit pas partir chez les élèves
        if c.structured_text and 'synthèse IA indisponible' in c.structured_text:
            skipped += 1
            continue
        c.publish()
        published += 1
    db.session.commit()
    return jsonify({'ok': True, 'published': published, 'skipped': skipped})

@teacher_corr_bp.route('/api/correction/<int:correction_id>/scores/update', methods=['POST'])
@login_required
def update_scores(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    max_by_id = {q.id: q.max_points for q in corr.assignment.questions}
    existing = {qs.question_id: qs for qs in corr.scores}
    for item in (request.get_json(silent=True) or {}).get('scores', []):
        qid = item.get('question_id')
        if qid not in max_by_id:
            continue
        try:
            val = float(item.get('score'))
        except (TypeError, ValueError):
            continue
        val = max(0.0, min(val, max_by_id[qid]))
        if qid in existing:
            existing[qid].score = val
        else:
            db.session.add(QuestionScore(correction_id=corr.id, question_id=qid, score=val))
    db.session.flush()
    db.session.expire(corr, ['scores'])
    corr.compute_total()
    db.session.commit()
    return jsonify({'ok': True, 'total_score': corr.total_score})

@teacher_corr_bp.route('/api/correction/<int:correction_id>/resynthesize', methods=['POST'])
@login_required
@limiter.limit("5 per minute; 20 per hour")
def resynthesize_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    if corr.status == 'published':
        return jsonify({'error': 'Impossible de modifier une correction publiée'}), 400
    if not corr.raw_transcript:
        return jsonify({'error': 'Aucune transcription disponible.'}), 400
    questions = corr.assignment.questions
    q_labels = [q.label for q in questions]
    q_max_points = [q.max_points for q in questions]
    q_ids = [q.id for q in questions]
    transcript = corr.raw_transcript
    app_ctx = current_app._get_current_object()

    def _do_resynthesize():
        with app_ctx.app_context():
            try:
                result = synthesize_with_mistral(transcript, q_labels, q_max_points)
                c = db.session.get(Correction, correction_id)
                if c:
                    c.structured_text = result.get('formatted_text') or transcript
                    _apply_ai_grades(c, result, q_ids, q_max_points)
                    c.status = 'draft'
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                app_ctx.logger.error(f'Resynthesize error corr {correction_id}: {e}')

    run_in_background(_do_resynthesize)
    return jsonify({'ok': True})

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
    try:
        result = synthesize_appreciation(raw)
    except Exception as e:
        print(f'[IA appréciation] {e}', flush=True)
        return jsonify({'error': "L'IA est indisponible, réessaie dans un instant."}), 503
    return jsonify({'ok': True, 'text': result})

@teacher_corr_bp.route('/correction/<int:correction_id>/pdf')
@login_required
def correction_pdf(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher_crud.dashboard'))
    card = _make_card(corr, with_qr=(corr.status == 'published'))
    return render_template('teacher/print_corrections.html', assignment=corr.assignment, cards=[card],
                           back_url=url_for('teacher_corr.correction_detail', correction_id=corr.id),
                           back_label='Retour à la correction')

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
    if comp.teacher_id != current_user.id:
        abort(403)
    try:
        Question.query.filter_by(competence_id=comp.id).update({'competence_id': None})
        db.session.delete(comp)
        db.session.commit()
        flash('Compétence supprimée.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Suppression compétence {comp_id}: {e}')
        flash('Suppression impossible : cette compétence est encore utilisée.', 'danger')
    return redirect(url_for('teacher_corr.list_competences'))