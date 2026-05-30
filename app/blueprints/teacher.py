from flask import (Blueprint, render_template, redirect, url_for,
                   request, jsonify, flash, send_file, current_app)
from flask_login import login_required, current_user
from app import db
from app.models import (Classroom, Student, Assignment, Question,
                        Correction, QuestionScore)
from app.services.anonymization import generate_alias, encrypt_name, decrypt_name
from app.services.ai import synthesize_with_mistral, synthesize_appreciation
from app.services.storage       import upload_audio
from app.services.qrcode        import make_qr, qr_png_bytes
from app.services.background    import run_in_background
from datetime import datetime
import io
import csv, io as _io
from flask import session
from datetime import datetime, timezone, timedelta

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    classrooms     = Classroom.query.filter_by(teacher_id=current_user.id).all()
    total_students = sum(len(c.students)    for c in classrooms)
    total_devoirs  = sum(len(c.assignments) for c in classrooms)
    return render_template('teacher/dashboard.html',
                           classrooms=classrooms,
                           total_students=total_students,
                           total_corrections=total_devoirs)


# ── Classes ───────────────────────────────────────────────────────────────────

@teacher_bp.route('/classes')
@login_required
def classes():
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id)\
                                .order_by(Classroom.name).all()
    return render_template('teacher/classes.html', classrooms=classrooms)


@teacher_bp.route('/classes/new', methods=['GET', 'POST'])
@login_required
def new_class():
    if request.method == 'POST':
        c = Classroom(
            teacher_id  = current_user.id,
            name        = request.form['name'].strip(),
            subject     = request.form.get('subject', '').strip(),
            school_year = request.form.get('school_year', '2025-2026'),
        )
        db.session.add(c)
        db.session.commit()
        flash(f'Classe « {c.name} » créée.', 'success')
        return redirect(url_for('teacher.class_detail', class_id=c.id))
    return render_template('teacher/new_class.html')


@teacher_bp.route('/classes/<int:class_id>')
@login_required
def class_detail(class_id):
    c = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    students = Student.query.filter_by(classroom_id=class_id)\
                            .order_by(Student.student_number).all()
    for s in students:
        try:
            s.display_first = decrypt_name(s.encrypted_first_name)
            s.display_last  = decrypt_name(s.encrypted_last_name)
        except Exception:
            s.display_first = s.display_last = '—'
    assignments = Assignment.query.filter_by(classroom_id=class_id)\
                                  .order_by(Assignment.date.desc()).all()
    return render_template('teacher/class_detail.html',
                           classroom=c, students=students, assignments=assignments)


# ── Élèves CRUD ───────────────────────────────────────────────────────────────

@teacher_bp.route('/classes/<int:class_id>/students/add', methods=['POST'])
@login_required
def add_student(class_id):
    Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    first  = request.form['first_name'].strip()
    last   = request.form['last_name'].strip()
    number = Student.query.filter_by(classroom_id=class_id).count() + 1
    s = Student(
        classroom_id         = class_id,
        alias                = generate_alias(first, last, number),
        student_number       = number,
        encrypted_first_name = encrypt_name(first),
        encrypted_last_name  = encrypt_name(last),
    )
    db.session.add(s)
    db.session.commit()
    flash(f'Élève ajouté — alias : {s.alias}.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))


@teacher_bp.route('/classes/<int:class_id>/students/<int:student_id>/edit',
                  methods=['GET', 'POST'])
@login_required
def edit_student(class_id, student_id):
    Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    s = Student.query.filter_by(id=student_id, classroom_id=class_id).first_or_404()
    if request.method == 'POST':
        first = request.form['first_name'].strip()
        last  = request.form['last_name'].strip()
        s.encrypted_first_name = encrypt_name(first)
        s.encrypted_last_name  = encrypt_name(last)
        s.alias = generate_alias(first, last, s.student_number)
        db.session.commit()
        flash('Élève mis à jour.', 'success')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    try:
        first = decrypt_name(s.encrypted_first_name)
        last  = decrypt_name(s.encrypted_last_name)
    except Exception:
        first = last = ''
    return render_template('teacher/edit_student.html',
                           classroom_id=class_id, student=s,
                           first=first, last=last)


@teacher_bp.route('/classes/<int:class_id>/students/<int:student_id>/delete',
                  methods=['POST'])
@login_required
def delete_student(class_id, student_id):
    Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    s = Student.query.filter_by(id=student_id, classroom_id=class_id).first_or_404()
    alias = s.alias
    db.session.delete(s)
    db.session.commit()
    flash(f'Élève {alias} supprimé.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/classes/<int:class_id>/delete', methods=['POST'])
@login_required
def delete_class(class_id):
    classroom = Classroom.query.filter_by(
        id=class_id, teacher_id=current_user.id
    ).first_or_404()
    db.session.delete(classroom)
    db.session.commit()
    flash(f'Classe "{classroom.name}" supprimée.', 'success')
    return redirect(url_for('teacher.classes'))

# ── Import CSV Pronote ────────────────────────────────────────────────────────

@teacher_bp.route('/classes/<int:class_id>/import/csv', methods=['POST'])
@login_required
def import_csv_class(class_id):
    """Importe des élèves dans une classe existante depuis un CSV Pronote."""
    classroom = Classroom.query.filter_by(
        id=class_id, teacher_id=current_user.id
    ).first_or_404()

    f = request.files.get('csv_file')
    if not f:
        flash('Aucun fichier sélectionné.', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))

    try:
        content = f.read().decode('latin-1')
        reader  = csv.DictReader(
            _io.StringIO(content),
            delimiter='\t' if '\t' in content.split('\n')[0] else ','
        )
        # Normalise les noms de colonnes (strip + lowercase)
        rows = list(reader)
        if not rows:
            flash('Fichier vide.', 'danger')
            return redirect(url_for('teacher.class_detail', class_id=class_id))

        # Détecte les colonnes Nom/Prénom (format simple ou Pronote complet)
        cols = {k.strip().lower(): k for k in rows[0].keys()}
        col_nom    = cols.get('nom')
        col_prenom = cols.get('prénom') or cols.get('prenom')
        if not col_nom or not col_prenom:
            flash('Colonnes "Nom" et "Prénom" introuvables dans le fichier.', 'danger')
            return redirect(url_for('teacher.class_detail', class_id=class_id))

        # Récupère les noms déjà présents pour éviter les doublons
        existing = set()
        for s in classroom.students:
            try:
                fn = decrypt_name(s.encrypted_first_name).strip().lower()
                ln = decrypt_name(s.encrypted_last_name).strip().lower()
                existing.add((ln, fn))
            except Exception:
                pass

        added = skipped = 0
        number = Student.query.filter_by(classroom_id=class_id).count()

        for row in rows:
            last  = row[col_nom].strip().strip('"')
            first = row[col_prenom].strip().strip('"')
            if not last or not first:
                continue
            if (last.lower(), first.lower()) in existing:
                skipped += 1
                continue
            number += 1
            db.session.add(Student(
                classroom_id         = class_id,
                alias                = generate_alias(first, last, number),
                student_number       = number,
                encrypted_first_name = encrypt_name(first),
                encrypted_last_name  = encrypt_name(last),
            ))
            existing.add((last.lower(), first.lower()))
            added += 1

        db.session.commit()
        flash(f'{added} élève(s) importé(s). {skipped} doublon(s) ignoré(s).', 'success')

    except Exception as e:
        flash(f'Erreur lors de l\'import : {e}', 'danger')

    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/import/pronote-file', methods=['POST'])
@login_required
def import_pronote_file():
    """Import CSV Pronote par classe — format Élèves;...;Classe de rattachement"""
    class_name = request.form.get('class_name', '').strip()
    subject    = request.form.get('subject', '').strip()
    year       = request.form.get('school_year', '2025-2026').strip()
    f          = request.files.get('csv_file')

    if not class_name or not f:
        flash('Nom de classe et fichier requis.', 'danger')
        return redirect(url_for('teacher.admin'))

    try:
        raw = f.read()
        # UTF-8 BOM en priorité, fallback latin-1
        try:
            content = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            content = raw.decode('latin-1')

        reader = csv.DictReader(_io.StringIO(content), delimiter=';')
        rows   = list(reader)

        if not rows:
            flash('Fichier vide.', 'danger')
            return redirect(url_for('teacher.admin'))

        # Trouve la colonne Élèves (insensible à la casse/BOM)
        col_eleves = None
        for k in rows[0].keys():
            if 'lève' in k.lower() or 'leve' in k.lower():
                col_eleves = k
                break
        if not col_eleves:
            col_eleves = list(rows[0].keys())[0]  # fallback première colonne

        # Cherche ou crée la classe
        classroom = Classroom.query.filter_by(
            teacher_id  = current_user.id,
            name        = class_name,
            school_year = year,
        ).first()
        if not classroom:
            classroom = Classroom(
                teacher_id  = current_user.id,
                name        = class_name,
                subject     = subject or None,
                school_year = year,
            )
            db.session.add(classroom)
            db.session.flush()

        # Élèves déjà présents (anti-doublon)
        existing = set()
        for s in classroom.students:
            try:
                fn = decrypt_name(s.encrypted_first_name).strip().lower()
                ln = decrypt_name(s.encrypted_last_name).strip().lower()
                existing.add((ln, fn))
            except Exception:
                pass

        number  = Student.query.filter_by(classroom_id=classroom.id).count()
        added   = skipped = 0

        import re
        for row in rows:
            eleve = row.get(col_eleves, '').strip().strip('"')
            if not eleve:
                continue
            # Format Pronote : "NOM(S) EN MAJUSCULES Prénom"
            # Regex : tout en caps = nom, première lettre min = début prénom
            m = re.match(
                r'^([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ\s\-]+?)\s+'
                r'([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][a-zàâäéèêëîïôöùûüç].+)$',
                eleve
            )
            if m:
                last, first = m.group(1).strip(), m.group(2).strip()
            else:
                parts = eleve.rsplit(' ', 1)
                last, first = (parts[0], parts[1]) if len(parts) == 2 else (eleve, '—')

            if (last.lower(), first.lower()) in existing:
                skipped += 1
                continue

            number += 1
            db.session.add(Student(
                classroom_id         = classroom.id,
                alias                = generate_alias(first, last, number),
                student_number       = number,
                encrypted_first_name = encrypt_name(first),
                encrypted_last_name  = encrypt_name(last),
            ))
            existing.add((last.lower(), first.lower()))
            added += 1

        db.session.commit()
        flash(
            f'Classe "{class_name}" : {added} élève(s) importé(s), '
            f'{skipped} doublon(s) ignoré(s).',
            'success'
        )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        flash(f'Erreur : {e}', 'danger')

    return redirect(url_for('teacher.admin'))

# ── Devoirs CRUD ──────────────────────────────────────────────────────────────

@teacher_bp.route('/assignments/new/<int:class_id>', methods=['GET', 'POST'])
@login_required
def new_assignment(class_id):
    c = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    if request.method == 'POST':
        a = Assignment(
            classroom_id = class_id,
            title        = request.form['title'].strip(),
            description  = request.form.get('description', ''),
            date         = datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            total_points = float(request.form.get('total_points', 20)),
        )
        db.session.add(a)
        db.session.flush()
        labels = request.form.getlist('q_label')
        maxpts = request.form.getlist('q_max')
        comps  = request.form.getlist('q_competence')
        for i, (lbl, mx, comp) in enumerate(zip(labels, maxpts, comps)):
            if lbl.strip():
                db.session.add(Question(
                    assignment_id = a.id,
                    label         = lbl.strip(),
                    max_points    = float(mx or 1),
                    competence    = comp.strip(),
                    order         = i,
                ))
        db.session.commit()
        flash(f'Devoir « {a.title} » créé.', 'success')
        # Redirige vers la vue corrections du devoir (lien micro par élève)
        return redirect(url_for('teacher.assignment_corrections', assignment_id=a.id))
    return render_template('teacher/new_assignment.html',
                           classroom=c, now=datetime.today())


@teacher_bp.route('/assignments/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_assignment(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    if request.method == 'POST':
        a.title        = request.form['title'].strip()
        a.description  = request.form.get('description', '')
        a.total_points = float(request.form.get('total_points', 20))
        a.date         = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        db.session.commit()
        flash('Devoir mis à jour.', 'success')
        return redirect(url_for('teacher.class_detail', class_id=a.classroom_id))
    return render_template('teacher/edit_assignment.html', assignment=a)


@teacher_bp.route('/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    class_id, title = a.classroom_id, a.title
    db.session.delete(a)
    db.session.commit()
    flash(f'Devoir « {title} » supprimé.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))


# ── Vue corrections d'un devoir ───────────────────────────────────────────────

@teacher_bp.route('/assignments/<int:assignment_id>/corrections')
@login_required
def assignment_corrections(assignment_id):
    """
    Vue centrale post-création devoir.
    Liste tous les élèves + statut correction + bouton micro direct.
    """
    a = Assignment.query.get_or_404(assignment_id)
    if a.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    students = Student.query.filter_by(classroom_id=a.classroom_id)\
                            .order_by(Student.student_number).all()
    for s in students:
        s.correction = Correction.query.filter_by(
            student_id=s.id, assignment_id=assignment_id
        ).first()
        try:
            s.display_last  = decrypt_name(s.encrypted_last_name)
            s.display_first = decrypt_name(s.encrypted_first_name)
        except Exception:
            s.display_last = s.display_first = '—'
    return render_template('teacher/assignment_corrections.html',
                           assignment=a, students=students)


# ── Enregistrement ────────────────────────────────────────────────────────────

@teacher_bp.route('/record/<int:student_id>/<int:assignment_id>')
@login_required
def record(student_id, assignment_id):
    student    = Student.query.get_or_404(student_id)
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    existing = Correction.query.filter_by(
        student_id=student_id, assignment_id=assignment_id
    ).first()
    return render_template('teacher/record.html',
                           student=student, assignment=assignment,
                           questions=assignment.questions, existing=existing)



@teacher_bp.route("/assignments/<int:assignment_id>/print")
@login_required
def print_corrections(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.classroom.teacher_id != current_user.id:
        flash("Accès non autorisé.", "danger")
        return redirect(url_for("teacher.dashboard"))
    students = Student.query.filter_by(classroom_id=a.classroom_id).order_by(Student.student_number).all()
    cards = []
    for s in students:
        try:
            first = decrypt_name(s.encrypted_first_name)
            last  = decrypt_name(s.encrypted_last_name)
        except Exception:
            first = last = "—"
        corr = Correction.query.filter_by(student_id=s.id, assignment_id=assignment_id, status="published").first()
        if not corr:
            continue
        qr = make_qr(corr.public_token)
        cards.append({"alias":s.alias,"first_name":first,"last_name":last,"score":corr.total_score,"text":corr.structured_text or "","qr_b64":qr["png_b64"],"qr_url":qr["url"]})
    cards.sort(key=lambda c: c["last_name"].lower())
    return render_template("teacher/print_corrections.html", assignment=a, cards=cards)

@teacher_bp.route('/correction/<int:correction_id>')
@login_required
def correction_detail(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    student = corr.student
    try:
        student.display_first = decrypt_name(student.encrypted_first_name)
        student.display_last  = decrypt_name(student.encrypted_last_name)
    except Exception:
        student.display_first = student.display_last = '—'
    qr = make_qr(corr.public_token) if corr.status == 'published' else {}
    return render_template('teacher/correction_detail.html',
                           correction=corr,
                           student=student,
                           qr_b64=qr.get('png_b64', ''),
                           qr_url=qr.get('url', ''))
# ── API JSON ──────────────────────────────────────────────────────────────────

@teacher_bp.route('/api/correction/save', methods=['POST'])
@login_required
def save_correction():
    data          = request.get_json()
    student_id    = data['student_id']
    assignment_id = data['assignment_id']
    transcript    = data.get('transcript', '')
    scores_data   = data.get('scores', [])

    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403

    corr = Correction.query.filter_by(
        student_id=student_id, assignment_id=assignment_id
    ).first()
    if not corr:
        corr = Correction(student_id=student_id, assignment_id=assignment_id)
        db.session.add(corr)

    corr.raw_transcript = transcript
    corr.status         = 'processing'

    # ── FIX 1 : flush d'abord pour avoir corr.id ──────────────────────────────
    db.session.flush()
    corr_id = corr.id

    QuestionScore.query.filter_by(correction_id=corr_id).delete()
    for s in scores_data:
        db.session.add(QuestionScore(
            correction_id = corr_id,
            question_id   = s['question_id'],
            score         = float(s['score']),
        ))

    corr.compute_total()
    db.session.commit()
    q_labels   = [q.label for q in assignment.questions]
    q_ids      = [q.id    for q in assignment.questions]
    app        = current_app._get_current_object()

    def _synthesize():
        with app.app_context():
            c = db.session.get(Correction, corr_id)
            if not c:
                return
            result = synthesize_with_mistral(c.raw_transcript, q_labels)
            c.structured_text = result.get('formatted_text', c.raw_transcript)
            if not scores_data:
                grades = result.get('grades', [])
                for ai_score in grades:
                    idx = ai_score.get('question_index')
                    # Fallback positionnel si Mistral n'a pas fourni question_index
                    if idx is None:
                        idx = grades.index(ai_score)
                    if idx is not None and idx < len(q_ids):
                        db.session.add(QuestionScore(
                            correction_id = corr_id,
                            question_id   = q_ids[idx],
                            score         = float(ai_score['score']),
                        ))
                db.session.flush()
                c.compute_total()
            c.status = 'draft'
            db.session.commit()

    run_in_background(_synthesize)
    return jsonify({'ok': True, 'correction_id': corr_id, 'token': corr.public_token})


@teacher_bp.route('/api/correction/<int:correction_id>/status')
@login_required
def correction_status(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr:
        return jsonify({'error': 'Introuvable'}), 404
    return jsonify({
        'status':          corr.status,
        'structured_text': corr.structured_text or '',
        'total_score':     corr.total_score,
    })

@teacher_bp.route('/api/correction/<int:correction_id>/scores')
@login_required
def correction_scores(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr:
        return jsonify([])
    return jsonify([
        {'question_id': s.question_id, 'score': s.score}
        for s in corr.scores
    ])


@teacher_bp.route('/api/correction/<int:correction_id>/audio', methods=['POST'])
@login_required
def upload_audio_route(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'Fichier manquant'}), 400
    try:
        result = upload_audio(audio_file.read(),
                              public_id=f'corr_{corr.public_token}',
                              teacher_id=current_user.id)
        corr.audio_url      = result['url']
        corr.audio_duration = result.get('duration')
        db.session.commit()
        return jsonify({'ok': True, 'audio_url': corr.audio_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@teacher_bp.route('/api/correction/<int:correction_id>/publish', methods=['POST'])
@login_required
def publish_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    corr.publish()
    db.session.commit()
    qr = make_qr(corr.public_token)
    return jsonify({'ok': True, 'qr': qr['png_b64'], 'url': qr['url']})


@teacher_bp.route('/correction/<int:correction_id>/qr.png')
@login_required
def download_qr(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return 'Non autorisé', 403
    classroom_name  = corr.assignment.classroom.name.replace(' ', '_')
    assignment_name = corr.assignment.title.replace(' ', '_')
    alias           = corr.student.alias.replace('-', '_')
    filename        = f'{classroom_name}_{assignment_name}_{alias}.png'
    return send_file(
        io.BytesIO(qr_png_bytes(corr.public_token)),
        mimetype      = 'image/png',
        as_attachment = True,
        download_name = filename,
    )

@teacher_bp.route('/assignments/<int:assignment_id>/appreciation', methods=['POST'])
@login_required
def save_appreciation(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    a.class_appreciation = request.get_json().get('text', '').strip() or None
    db.session.commit()
    return jsonify({'ok': True})

@teacher_bp.route('/assignments/<int:assignment_id>/appreciation/synthesize',
                  methods=['POST'])
@login_required
def synthesize_appreciation_route(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    raw = request.get_json().get('text', '').strip()
    if not raw:
        return jsonify({'error': 'Texte vide'}), 400
    app_ctx = current_app._get_current_object()
    # Appel synchrone (texte court, rapide)
    result = synthesize_appreciation(raw)
    return jsonify({'ok': True, 'text': result})

# ── Admin ─────────────────────────────────────────────────────────────────────
 
@teacher_bp.route('/admin')
@login_required
def admin():
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id)\
                                .order_by(Classroom.name).all()
    lock_error = session.pop('admin_lock_error', None)
    return render_template('teacher/admin.html',
                           classrooms=classrooms,
                           lock_error=lock_error)
 
 
@teacher_bp.route('/admin/unlock', methods=['POST'])
@login_required
def admin_unlock():
    password = request.form.get('password', '')
    if current_user.check_password(password):
        session['admin_unlocked']    = True
        session['admin_unlocked_at'] = datetime.now(timezone.utc).isoformat()
        return redirect(url_for('teacher.admin'))
    else:
        session['admin_lock_error'] = 'Mot de passe incorrect.'
        return redirect(url_for('teacher.admin'))
 
 
@teacher_bp.route('/admin/lock')
@login_required
def admin_lock():
    session.pop('admin_unlocked', None)
    session.pop('admin_unlocked_at', None)
    return redirect(url_for('teacher.dashboard'))
 
 
@teacher_bp.route('/admin/theme', methods=['POST'])
@login_required
def admin_theme():
    if not session.get('admin_unlocked'):
        return redirect(url_for('teacher.admin'))
    themes = {
        'neon':    {'primary': '#39FF14', 'secondary': '#0a0a0a', 'bg': '#ffffff'},
        'ardoise': {'primary': '#6366f1', 'secondary': '#1e293b', 'bg': '#f8fafc'},
        'soleil':  {'primary': '#f59e0b', 'secondary': '#92400e', 'bg': '#fffbeb'},
        'ocean':   {'primary': '#0ea5e9', 'secondary': '#0c4a6e', 'bg': '#f0f9ff'},
        'craie':   {'primary': '#000000', 'secondary': '#374151', 'bg': '#ffffff'},
    }
    t = themes.get(request.form.get('theme', 'neon'))
    if t:
        current_user.theme_primary   = t['primary']
        current_user.theme_secondary = t['secondary']
        current_user.theme_bg        = t['bg']
        db.session.commit()
        flash('Thème appliqué.', 'success')
    return redirect(url_for('teacher.admin'))
 
 
@teacher_bp.route('/admin/delete-account', methods=['POST'])
@login_required
def admin_delete_account():
    if not session.get('admin_unlocked'):
        return redirect(url_for('teacher.admin'))
    confirm  = request.form.get('confirm', '')
    password = request.form.get('password', '')
    if confirm != 'SUPPRIMER' or not current_user.check_password(password):
        flash('Confirmation incorrecte.', 'danger')
        return redirect(url_for('teacher.admin'))
    # Supprime le teacher (cascade supprime tout via SQLAlchemy)
    from flask_login import logout_user
    user = current_user._get_current_object()
    logout_user()
    db.session.delete(user)
    db.session.commit()
    flash('Compte supprimé.', 'success')
    return redirect(url_for('auth.login'))
 
 
@teacher_bp.route('/admin/export/notes', methods=['POST'])
@login_required
def admin_export_notes():
    if not session.get('admin_unlocked'):
        return redirect(url_for('teacher.admin'))

    class_ids = request.form.getlist('class_ids', type=int)
    date_from_str = request.form.get('date_from')
    date_to_str   = request.form.get('date_to')

    # Parse des dates optionnelles
    try:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date() if date_from_str else None
        date_to   = datetime.strptime(date_to_str,   '%Y-%m-%d').date() if date_to_str   else None
    except ValueError:
        date_from = date_to = None

    # Classes sélectionnées (toutes si aucune cochée)
    query = Classroom.query.filter_by(teacher_id=current_user.id)
    if class_ids:
        query = query.filter(Classroom.id.in_(class_ids))
    classrooms = query.all()

    if not classrooms:
        flash('Aucune classe sélectionnée.', 'warning')
        return redirect(url_for('teacher.admin'))

    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Classe', 'Élève', 'Devoir', 'Date', 'Note', 'Sur', 'Statut'])

    for classroom in classrooms:
        for assignment in classroom.assignments:
            # Filtre date
            if date_from and assignment.date and assignment.date < date_from:
                continue
            if date_to and assignment.date and assignment.date > date_to:
                continue
            for correction in assignment.corrections:
                try:
                    first = decrypt_name(correction.student.encrypted_first_name)
                    last  = decrypt_name(correction.student.encrypted_last_name)
                    name  = f"{last} {first}"
                except Exception:
                    name = correction.student.alias
                writer.writerow([
                    classroom.name,
                    name,
                    assignment.title,
                    assignment.date.strftime('%d/%m/%Y') if assignment.date else '',
                    correction.total_score if correction.total_score is not None else '',
                    assignment.total_points,
                    correction.status,
                ])

    output.seek(0)
    filename = f"notes_export_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )