from flask import (Blueprint, render_template, redirect, url_for,
                   request, jsonify, flash, send_file, current_app)
from flask_login import login_required, current_user
from app import db, csrf
from app.models import (Classroom, Student, Assignment, Question,
                        Correction, QuestionScore, ClassroomTeacher, Group, GroupStudent, Teacher)
from app.services.anonymization import generate_alias, encrypt_name, decrypt_name
from app.services.ai import synthesize_with_mistral, synthesize_appreciation
from app.services.storage       import upload_audio
from app.services.qrcode        import make_qr, qr_png_bytes
from app.services.background    import run_in_background
from app.services.tts import generate_tts_audio
import io
import csv, io as _io
from flask import session
from datetime import datetime, timezone, timedelta

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

# ── Assainissement des données importées ─────────────────────────────────────────────────────────────────
def sanitize_csv_field(value):
    if not value:
        return value
    value = str(value)
    if value.startswith(('=', '+', '-', '@')):
        return "\t" + value  # Tabulation
    return value

# ── Vérification Timestamp ─────────────────────────────────────────────────────────────────
def is_admin_session_valid():
    """Vérifie que la session admin a moins de 30 minutes"""
    unlocked_at = session.get('admin_unlocked_at')
    if not unlocked_at:
        return False
    try:
        unlocked_dt = datetime.fromisoformat(unlocked_at)
        return datetime.now(timezone.utc) - unlocked_dt < timedelta(minutes=30)
    except Exception:
        return False

# ── Dashboard ─────────────────────────────────────────────────────────────────

@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    classrooms     = Classroom.query.filter_by(teacher_id=current_user.id).all()
    total_students = sum(len(c.students)    for c in classrooms)
    total_devoirs  = sum(len(c.assignments) for c in classrooms)
    # Calcul du taux de correction par devoir
    assign_stats = {}
    for c in classrooms:
        total = len(c.students)
        for a in c.assignments:
            done = Correction.query.filter_by(
                assignment_id=a.id, status='published'
            ).count()
            pct = int(done / total * 100) if total > 0 else 0
            assign_stats[a.id] = {'done': done, 'total': total, 'pct': pct}

    return render_template('teacher/dashboard.html',
        classrooms=classrooms,
        assign_stats=assign_stats,
        total_students=total_students,
        total_corrections=total_devoirs,
    )


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
        current_app.logger.error(f'Import CSV error: {e}')
        flash("Erreur lors de l'import. Vérifiez le format du fichier.", 'danger')

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
        current_app.logger.error(traceback.format_exc())
        flash('Une erreur est survenue lors de l\'import. Vérifiez le format du fichier.', 'danger')

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
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
    if a.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    if request.method == 'POST':
        a.title       = request.form['title'].strip()
        a.description = request.form.get('description', '')
        a.date        = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        a.total_points = float(request.form.get('total_points', 20))

        # Mise à jour des questions existantes
        for q in a.questions:
            label      = request.form.get(f'q_label_{q.id}', '').strip()
            competence = request.form.get(f'q_competence_{q.id}', '').strip()
            new_max    = request.form.get(f'q_max_{q.id}')
            force_clamp = request.form.get(f'q_clamp_{q.id}') == '1'

            if label:
                q.label = label
            q.competence = competence

            if new_max is not None:
                new_max = float(new_max)
                if new_max != q.max_points:
                    if force_clamp:
                        # Reclamper tous les scores existants
                        for qs in QuestionScore.query.filter_by(question_id=q.id).all():
                            if qs.score is not None and qs.score > new_max:
                                qs.score = new_max
                        # Recalculer les totaux affectés
                        affected = {qs.correction_id for qs in QuestionScore.query.filter_by(question_id=q.id).all()}
                        for corr in Correction.query.filter(Correction.id.in_(affected)).all():
                            corr.compute_total()
                    q.max_points = new_max

        db.session.commit()
        flash('Devoir mis à jour.', 'success')
        return redirect(url_for('teacher.class_detail', class_id=a.classroom_id))

    # Compte les corrections existantes par question
    questions_data = []
    for q in a.questions:
        count = QuestionScore.query.filter_by(question_id=q.id).count()
        questions_data.append({'question': q, 'corrections_count': count})

    return render_template('teacher/edit_assignment.html',
                           assignment=a,
                           questions_data=questions_data)


@teacher_bp.route('/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
    if a.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    class_id, title = a.classroom_id, a.title
    db.session.delete(a)
    db.session.commit()
    flash(f'Devoir « {title} » supprimé.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))


# ── STATISTIQUES ELEVES ───────────────────────────────────────────────
@teacher_bp.route('/api/stats/class/<int:class_id>')
@login_required
def class_stats(class_id):
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    # Récupérer tous les devoirs avec leurs corrections
    data = {
        'labels': [],
        'scores': [],
        'competences': {}
    }
    for assignment in classroom.assignments:
        data['labels'].append(assignment.title)
        avg_score = sum(c.total_score or 0 for c in assignment.corrections) / max(len(assignment.corrections),1)
        data['scores'].append(avg_score)
    return jsonify(data)

# ── Vue corrections d'un devoir ───────────────────────────────────────────────

@teacher_bp.route('/assignments/<int:assignment_id>/corrections')
@login_required
def assignment_corrections(assignment_id):
    """
    Vue centrale post-création devoir.
    Liste tous les élèves + statut correction + bouton micro direct.
    """
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
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
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)
    try:
        student_first = decrypt_name(student.encrypted_first_name)
        student_last  = decrypt_name(student.encrypted_last_name)
    except Exception:
        student_first = student_last = '—'
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        abort(404)
    if assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    
    # Vérifier que l'élève appartient bien à la classe du devoir
    student = db.session.get(Student, student_id)
    if not student or student.classroom_id != assignment.classroom_id:
        return jsonify({'error': 'Élève non trouvé dans cette classe'}), 404
    
    corr = Correction.query.filter_by(
        student_id=student_id, assignment_id=assignment_id
    ).first()

    # Tri alphabétique par nom de famille déchiffré (ordre Pronote)
    all_students = Student.query.filter_by(classroom_id=assignment.classroom_id).all()
    def _sort_key(s):
        try:
            return decrypt_name(s.encrypted_last_name).lower()
        except Exception:
            return s.alias.lower()
    all_students.sort(key=_sort_key)

    ids = [s.id for s in all_students]
    try:
        idx = ids.index(student_id)
    except ValueError:
        idx = 0

    prev_id = ids[idx - 1] if idx > 0 else None
    next_id = ids[idx + 1] if idx < len(ids) - 1 else None

    def _has_correction(sid):
        if sid is None:
            return False
        return Correction.query.filter_by(
            student_id=sid, assignment_id=assignment_id
        ).first() is not None

    return render_template('teacher/record.html',
                           student=student, assignment=assignment,
                           questions=assignment.questions, existing=existing,
                           prev_student_id=prev_id,
                           next_student_id=next_id,
                           has_prev_correction=_has_correction(prev_id),
                           has_next_correction=_has_correction(next_id),
                           student_index=idx + 1,
                           student_first=student_first,
                           student_last=student_last,
                           student_total=len(ids))



@teacher_bp.route("/assignments/<int:assignment_id>/print")
@login_required
def print_corrections(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
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

@teacher_bp.route('/correction/<int:correction_id>/preview')
@login_required
def preview_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    # Si déjà publié, rediriger vers la vraie page élève
    if corr.status == 'published':
        return redirect(url_for('public.student_view', token=corr.public_token))

    # Whitelist des statuts autorisés pour l'aperçu
    PREVIEWABLE_STATUSES = ('draft',)
    if corr.status not in PREVIEWABLE_STATUSES:
        flash(
            f"Aperçu non disponible — correction en statut « {corr.status} »."
            " Revenez dans quelques instants.",
            "warning"
        )
        return redirect(url_for('teacher.correction_detail', correction_id=correction_id))

    scores_detail = [
        {
            'label':      qs.question.label,
            'score':      qs.score,
            'max':        qs.question.max_points,
            'competence': qs.question.competence,
        }
        for qs in corr.scores
    ]

    return render_template(
        'public/student.html',
        correction=corr,
        scores=scores_detail,
        teacher=corr.assignment.classroom.teacher,
        preview_mode=True
    )
# ── API JSON ──────────────────────────────────────────────────────────────────

@teacher_bp.route('/api/correction/save', methods=['POST'])
@login_required
@limiter.limit("10 per minute; 50 per hour")
def save_correction():
    data          = request.get_json()
    student_id    = data['student_id']
    assignment_id = data['assignment_id']
    transcript    = data.get('transcript', '')
    scores_data   = data.get('scores', [])

    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        abort(404)
    if assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    
    # Vérifier que l'élève appartient bien à la classe du devoir
    student = db.session.get(Student, student_id)
    if not student or student.classroom_id != assignment.classroom_id:
        return jsonify({'error': 'Élève invalide pour cette classe'}), 404

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

    q_max_by_id = {q.id: q.max_points for q in assignment.questions}
    QuestionScore.query.filter_by(correction_id=corr_id).delete()
    for s in scores_data:
        max_pts = q_max_by_id.get(s['question_id'])
        score   = min(float(s['score']), max_pts) if max_pts is not None else float(s['score'])
        db.session.add(QuestionScore(
            correction_id = corr_id,
            question_id   = s['question_id'],
            score         = score,
        ))

    corr.compute_total()
    db.session.commit()
    q_labels = [q.label      for q in assignment.questions]
    q_ids    = [q.id         for q in assignment.questions]
    q_max    = [q.max_points for q in assignment.questions]
    app      = current_app._get_current_object()

    def _synthesize():
        with app.app_context():
            c = db.session.get(Correction, corr_id)
            if not c:
                return
            try:
                result = synthesize_with_mistral(c.raw_transcript, q_labels, q_max)
                c.structured_text = result.get('formatted_text', c.raw_transcript)

                # Récupère les scores déjà existants (saisis manuellement avant le thread)
                existing_scores = {qs.question_id: qs for qs in c.scores}

                grades = result.get('grades', [])
                for ai_score in grades:
                    idx = ai_score.get('question_index')
                    if idx is None:
                        idx = grades.index(ai_score)
                    if idx is None or idx >= len(q_ids):
                        continue
                    qid = q_ids[idx]
                    # Si un score existe déjà pour cette question (manuel), on ne l'écrase pas
                    if qid in existing_scores:
                        continue
                    raw_score = float(ai_score['score'])
                    safe_score = min(raw_score, q_max[idx])
                    advice_text = ai_score.get('advice', '')
                    # Création du nouveau score
                    qs = QuestionScore(
                        correction_id=corr_id,
                        question_id=qid,
                        score=safe_score,
                        advice=advice_text
                    )
                    db.session.add(qs)
                    existing_scores[qid] = qs  # mise à jour du dict

                db.session.flush()
                c.compute_total()
                c.status = 'draft'
                db.session.commit()

            except Exception as e:
                db.session.rollback()
                c.status = 'draft'
                db.session.commit()
                # Optionnel : log de l'erreur
                print(f"[Mistral] Erreur dans _synthesize: {e}")

@teacher_bp.route('/api/correction/<int:correction_id>/status')
@login_required
def correction_status(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 404
    return jsonify({
        'status':          corr.status,
        'structured_text': corr.structured_text or '',
        'total_score':     corr.total_score,
    })

@teacher_bp.route('/api/correction/<int:correction_id>/scores')
@login_required
def correction_scores(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify([])
    return jsonify([
        {'question_id': s.question_id, 'score': s.score}
        for s in corr.scores
    ])


@teacher_bp.route('/api/correction/<int:correction_id>/audio', methods=['POST'])
@login_required
@csrf.protect
def upload_audio_route(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'Fichier manquant'}), 400
    
    # Validation du type de fichier (sans python-magic)
    ALLOWED_EXTENSIONS = {'webm', 'mp3', 'wav', 'm4a', 'ogg'}
    extension = audio_file.filename.rsplit('.', 1)[-1].lower() if '.' in audio_file.filename else ''
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'Extension .{extension} non autorisée. Types acceptés: webm, mp3, wav, m4a, ogg'}), 400
    
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
@csrf.protect
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

@teacher_bp.route('/api/correction/<int:correction_id>/delete', methods=['POST'])
@login_required
@csrf.protect
def delete_correction(correction_id):
    """Suppression définitive d'une correction (unitaire).
    Body JSON : { "password": "..." }
    """
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403

    data = request.get_json(silent=True) or {}
    if not current_user.check_password(data.get('password', '')):
        return jsonify({'error': 'Mot de passe incorrect'}), 403

    assignment_id = corr.assignment_id
    db.session.delete(corr)
    db.session.commit()
    return jsonify({'ok': True, 'assignment_id': assignment_id})


@teacher_bp.route('/api/corrections/delete-bulk', methods=['POST'])
@login_required
@csrf.protect
def delete_corrections_bulk():
    """Suppression groupée de plusieurs corrections.
    Body JSON : { "ids": [1, 2, 3], "password": "..." }
    """
    data = request.get_json(silent=True) or {}
    if not current_user.check_password(data.get('password', '')):
        return jsonify({'error': 'Mot de passe incorrect'}), 403

    ids = data.get('ids', [])
    # Limiter à 100 suppressions par requête (évite DoS)
    if len(ids) > 100:
        return jsonify({'error': 'Trop de corrections sélectionnées (max 100)'}), 400
    if not ids:
        return jsonify({'error': 'Aucune correction sélectionnée'}), 400

    deleted = 0
    for cid in ids:
        corr = db.session.get(Correction, cid)
        if corr and corr.assignment.classroom.teacher_id == current_user.id:
            db.session.delete(corr)
            deleted += 1

    db.session.commit()
    return jsonify({'ok': True, 'deleted': deleted})

@teacher_bp.route('/api/correction/<int:correction_id>/resynthesize', methods=['POST'])
@login_required
@limiter.limit("5 per minute; 20 per hour")
def resynthesize_correction(correction_id):
    """Relance Mistral sur le raw_transcript existant, sans toucher à l'audio ni aux scores."""
    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403

    if corr.status == 'published':
        return jsonify({'error': 'Impossible de modifier une correction publiée'}), 400

    if not corr.raw_transcript:
        return jsonify({'error': 'Aucune transcription disponible — veuillez ré-enregistrer.'}), 400

    # Prépare les labels et max_points pour Mistral
    questions    = corr.assignment.questions
    q_labels     = [q.label     for q in questions]
    q_max_points = [q.max_points for q in questions]

    app_ctx = current_app._get_current_object()

    def _do_resynthesize():
        with app_ctx.app_context():
            try:
                result = synthesize_with_mistral(
                    corr.raw_transcript, q_labels, q_max_points
                )
                corr.structured_text = result.get('formatted_text', corr.raw_transcript)
                corr.status = 'draft'
                db.session.commit()
            except Exception as e:
                app_ctx.logger.error(f'Resynthesize error corr {correction_id}: {e}')

    run_in_background(_do_resynthesize)
    return jsonify({'ok': True})

@teacher_bp.route('/assignments/<int:assignment_id>/appreciation', methods=['POST'])
@login_required
@csrf.protect
def save_appreciation(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
    if a.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    a.class_appreciation = request.get_json().get('text', '').strip() or None
    db.session.commit()
    return jsonify({'ok': True})

@teacher_bp.route('/assignments/<int:assignment_id>/appreciation/synthesize',
                  methods=['POST'])
@login_required
@limiter.limit("5 per minute; 20 per hour")
def synthesize_appreciation_route(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a:
        abort(404)
    if a.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    raw = request.get_json().get('text', '').strip()
    if not raw:
        return jsonify({'error': 'Texte vide'}), 400
    app_ctx = current_app._get_current_object()
    # Appel synchrone (texte court, rapide)
    result = synthesize_appreciation(raw)
    return jsonify({'ok': True, 'text': result})

@teacher_bp.route('/classes/<int:class_id>/add-teacher', methods=['POST'])
@login_required
def add_teacher_to_class(class_id):
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    email = request.form.get('email', '').strip().lower()
    teacher = Teacher.query.filter_by(email=email).first()
    if not teacher:
        flash('Enseignant non trouvé.', 'danger')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    if teacher.id == current_user.id:
        flash('Vous ne pouvez pas vous ajouter vous-même.', 'warning')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    existing = ClassroomTeacher.query.filter_by(classroom_id=class_id, teacher_id=teacher.id).first()
    if existing:
        flash('Cet enseignant est déjà dans la classe.', 'warning')
    else:
        ct = ClassroomTeacher(classroom_id=class_id, teacher_id=teacher.id, role='editor')
        db.session.add(ct)
        db.session.commit()
        flash(f'{teacher.full_name} ajouté à la classe.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/classes/<int:class_id>/group/add', methods=['POST'])
@login_required
@csrf.protect
def add_group(class_id):
    classroom = db.session.get(Classroom, class_id)
    if not classroom or classroom.teacher_id != current_user.id:
        abort(404)
    name = request.form.get('group_name', '').strip()
    if name:
        group = Group(classroom_id=class_id, name=name)
        db.session.add(group)
        db.session.commit()
        flash(f'Groupe "{name}" créé.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/classes/<int:class_id>/group/<int:group_id>/delete', methods=['POST'])
@login_required
@csrf.protect
def delete_group(class_id, group_id):
    classroom = db.session.get(Classroom, class_id)
    if not classroom or classroom.teacher_id != current_user.id:
        abort(404)
    group = db.session.get(Group, group_id)
    if not group:
        abort(404)
    if group.classroom_id != class_id:
        abort(403)
    db.session.delete(group)
    db.session.commit()
    flash('Groupe supprimé.', 'success')
    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/classes/<int:class_id>/group/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
@csrf.protect
def edit_group(class_id, group_id):
    classroom = db.session.get(Classroom, class_id)
    if not classroom or classroom.teacher_id != current_user.id:
        abort(404)
    group = db.session.get(Group, group_id)
    if not group:
        abort(404)
    if group.classroom_id != class_id:
        abort(403)
    if request.method == 'POST':
        group.name = request.form.get('name', '').strip()
        # Mise à jour des membres
        student_ids = request.form.getlist('student_ids', type=int)
        GroupStudent.query.filter_by(group_id=group_id).delete()
        for sid in student_ids:
            db.session.add(GroupStudent(group_id=group_id, student_id=sid))
        db.session.commit()
        flash('Groupe mis à jour.', 'success')
        return redirect(url_for('teacher.class_detail', class_id=class_id))
    students = Student.query.filter_by(classroom_id=class_id).all()
    members = {gs.student_id for gs in group.students}
    return render_template('teacher/edit_group.html', classroom=classroom, group=group, students=students, members=members)

@teacher_bp.route('/api/student/<int:student_id>/competence-stats')
@login_required
def student_competence_stats(student_id):
    student = Student.query.get_or_404(student_id)
    if student.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    
    # Récupère toutes les corrections publiées de l'élève
    corrections = Correction.query.filter_by(
        student_id=student_id, 
        status='published'
    ).order_by(Correction.created_at).all()
    
    if not corrections:
        return jsonify({'competences': [], 'evolution': []})
    
    # Dictionnaire pour stocker les scores par compétence et par devoir
    # Structure: {competence_name: {assignment_title: score, ...}}
    comp_scores = {}
    evolution = []
    
    for corr in corrections:
        assignment_title = corr.assignment.title
        evolution.append({'devoir': assignment_title, 'note': corr.total_score})
        
        for qs in corr.scores:
            if not qs.question.competence:
                continue
            comp_name = qs.question.competence
            if comp_name not in comp_scores:
                comp_scores[comp_name] = {}
            comp_scores[comp_name][assignment_title] = qs.score
    
    # Calcul de la moyenne par compétence
    competence_stats = []
    for comp_name, scores in comp_scores.items():
        avg = sum(scores.values()) / len(scores) if scores else 0
        # Tendance (dernier score vs avant-dernier)
        values = list(scores.values())
        trend = values[-1] - values[-2] if len(values) >= 2 else 0
        competence_stats.append({
            'name': comp_name,
            'average': round(avg, 1),
            'trend': round(trend, 1),
            'scores': scores
        })
    
    # Tri par moyenne décroissante
    competence_stats.sort(key=lambda x: x['average'], reverse=True)
    
    return jsonify({
        'competences': competence_stats,
        'evolution': evolution,
        'student_name': f"{student.alias}"
    })

@teacher_bp.route('/api/student/<int:student_id>/prediction')
@login_required
def student_prediction(student_id):
    student = Student.query.get_or_404(student_id)
    if student.classroom.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403
    
    # Récupère les 5 dernières corrections
    corrections = Correction.query.filter_by(
        student_id=student_id, 
        status='published'
    ).order_by(Correction.created_at.desc()).limit(5).all()
    
    if len(corrections) < 3:
        return jsonify({
            'risk': 'insuffisant',
            'message': 'Pas assez de données (minimum 3 corrections)',
            'color': 'gray'
        })
    
    # Calcul de la moyenne des notes
    scores = [c.total_score or 0 for c in corrections]
    avg_score = sum(scores) / len(scores)
    last_score = scores[0] if scores else 0
    
    # Tendance (moyenne glissante)
    if len(scores) >= 2:
        prev_avg = sum(scores[1:]) / len(scores[1:])
        trend = last_score - prev_avg
    else:
        trend = 0
    
    # Seuils (à ajuster selon ton barème)
    if avg_score < 10:
        risk = 'élevé'
        message = "L'élève a des difficultés persistantes. Intervention recommandée."
        color = 'red'
    elif avg_score < 12:
        if trend < -2:
            risk = 'élevé'
            message = "Baisse récente préoccupante. À surveiller."
            color = 'orange'
        else:
            risk = 'moyen'
            message = "Résultats fragiles. Travail à consolider."
            color = 'orange'
    elif avg_score < 15:
        risk = 'faible'
        message = "Bonnes performances générales. Continuer ainsi."
        color = 'green'
    else:
        risk = 'très faible'
        message = "Excellent niveau. Peut viser plus haut."
        color = 'green'
    
    # Si tendance négative forte, on alerte même si moyenne correcte
    if trend < -3 and avg_score >= 12:
        risk = 'moyen'
        message = "Baisse récente inhabituelle. Vérifier la compréhension."
        color = 'orange'
    
    return jsonify({
        'risk': risk,
        'message': message,
        'color': color,
        'avg_score': round(avg_score, 1),
        'last_score': round(last_score, 1),
        'trend': round(trend, 1),
        'corrections_count': len(corrections)
    })

# ── Admin ─────────────────────────────────────────────────────────────────────
 
@teacher_bp.route('/admin')
@login_required
def admin():
    if not session.get('admin_unlocked') or not is_admin_session_valid():
        return redirect(url_for('teacher.admin_login'))
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
    if not session.get('admin_unlocked') or not is_admin_session_valid():
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
    if not session.get('admin_unlocked') or not is_admin_session_valid():
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
    if not session.get('admin_unlocked') or not is_admin_session_valid():
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
    
    # Écrire l'en-tête une seule fois (avec des chaînes littérales, pas des variables)
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
                    sanitize_csv_field(classroom.name),
                    sanitize_csv_field(name),
                    sanitize_csv_field(assignment.title),
                    sanitize_csv_field(assignment.date.strftime('%d/%m/%Y') if assignment.date else ''),
                    sanitize_csv_field(correction.total_score if correction.total_score is not None else ''),
                    sanitize_csv_field(assignment.total_points),
                    sanitize_csv_field(correction.status),
                ])

    output.seek(0)
    filename = f"notes_export_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )

# ______________________ EXPORT PDF CORRECTION __________________________

@teacher_bp.route('/correction/<int:correction_id>/pdf')
@login_required
def correction_pdf(correction_id):
    from weasyprint import HTML
    from app.services.qrcode import make_qr

    corr = db.session.get(Correction, correction_id)
    if not corr or corr.assignment.classroom.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    student = corr.student
    scores_detail = [
        {
            'label':      qs.question.label,
            'score':      qs.score,
            'max':        qs.question.max_points,
            'competence': qs.question.competence,
        }
        for qs in corr.scores
    ]

    qr_url  = f"{current_app.config['APP_BASE_URL']}/c/{corr.public_token}"
    qr_data = make_qr(corr.public_token) if corr.status == 'published' else None
    qr_b64  = qr_data['png_b64'] if qr_data else None

    html_str = render_template(
        'teacher/correction_pdf.html',
        correction=corr,
        student=student,
        scores=scores_detail,
        qr_b64=qr_b64,
        qr_url=qr_url if corr.status == 'published' else None,
        teacher=corr.assignment.classroom.teacher,
        now=datetime.now(timezone.utc),
    )

    try:
        pdf = HTML(string=html_str, base_url=request.host_url).write_pdf()
    except Exception:
        flash("Erreur lors de la génération du PDF.", "danger")
        return redirect(url_for('teacher.correction_detail', correction_id=correction_id))

    return current_app.response_class(
        pdf,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="correction-{student.alias}-{corr.assignment.title}.pdf"'
        }
    )

@teacher_bp.route('/api/tts/<int:correction_id>')
@login_required
def tts_correction(correction_id):
    corr = db.session.get(Correction, correction_id)
    if not corr:
        abort(404)
    if corr.assignment.classroom.teacher_id != current_user.id:
        abort(403)
    if not corr.structured_text:
        return jsonify({'error': 'Aucune synthèse disponible'}), 404
    audio_bytes = generate_tts_audio(corr.structured_text)
    return send_file(
        io.BytesIO(audio_bytes),
        mimetype='audio/mpeg',
        as_attachment=False,
        download_name=f'correction_{correction_id}.mp3'
    )