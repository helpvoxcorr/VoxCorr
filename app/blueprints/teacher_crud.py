from flask import (Blueprint, render_template, redirect, url_for,
                   request, jsonify, flash, current_app, json, abort)
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.models import (Classroom, Student, Assignment, Question,
                        ClassroomTeacher, Group, GroupStudent, Teacher, Competence, Correction)
from app.services.anonymization import generate_alias, encrypt_name, decrypt_name
import io
import csv
import re
from datetime import datetime, timezone

teacher_crud_bp = Blueprint('teacher_crud', __name__, url_prefix='/teacher')

def sanitize_csv_field(value):
    if not value: return value
    value = str(value)
    if value.startswith(('=', '+', '-', '@')): return "\t" + value
    return value

@teacher_crud_bp.route('/dashboard')
@login_required
def dashboard():
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id).order_by(Classroom.name).all()
    total_students = sum(len(c.students) for c in classrooms)
    total_assignments = sum(len(c.assignments) for c in classrooms)
    todo, finished = [], []
    corrected_total = expected_total = 0

    for c in classrooms:
        students = sorted(c.students, key=lambda s: s.student_number or 0)
        student_ids = {s.id for s in students}
        total = len(students)
        for a in c.assignments:
            corrected_ids = {row[0] for row in db.session.query(Correction.student_id)
                             .filter_by(assignment_id=a.id).all()}
            published = db.session.query(db.func.count(Correction.id)) \
                .filter_by(assignment_id=a.id, status='published').scalar() or 0
            done = len(corrected_ids & student_ids)
            drafts = max(done - published, 0)
            nxt = next((s for s in students if s.id not in corrected_ids), None)
            next_name = ''
            if nxt:
                try:
                    next_name = f"{decrypt_name(nxt.encrypted_last_name)} {decrypt_name(nxt.encrypted_first_name)}"
                except Exception:
                    next_name = nxt.alias
            item = {
                'assignment': a, 'classroom': c, 'total': total, 'done': done,
                'published': published, 'drafts': drafts,
                'pct': int(done / total * 100) if total else 0,
                'next_id': nxt.id if nxt else None, 'next_name': next_name,
            }
            corrected_total += done
            expected_total += total
            if total > 0 and done >= total and drafts == 0:
                finished.append(item)
            else:
                todo.append(item)

    def _by_date(t):
        return t['assignment'].date.isoformat() if t['assignment'].date else ''
    todo.sort(key=_by_date, reverse=True)
    finished.sort(key=_by_date, reverse=True)

    return render_template('teacher/dashboard.html', classrooms=classrooms,
                           total_students=total_students, total_assignments=total_assignments,
                           corrected_total=corrected_total, expected_total=expected_total,
                           todo=todo, finished=finished)

@teacher_crud_bp.route('/classes')
@login_required
def classes():
    LEVELS = ['6ème', '5ème', '4ème', '3ème', '2nde', '1ère', 'Terminale', 'Autre', None]
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id).order_by(Classroom.name).all()
    grouped = {}
    for lvl in LEVELS:
        key = lvl or 'Non classé'
        items = [c for c in classrooms if (c.level or None) == lvl]
        if items: grouped[key] = items
    return render_template('teacher/classes.html', classrooms=classrooms, grouped=grouped)

def _default_school_year():
    now = datetime.now()
    start = now.year if now.month >= 8 else now.year - 1
    return f'{start}-{start + 1}'

CLASS_LEVELS = ['6ème', '5ème', '4ème', '3ème', '2nde', '1ère', 'Terminale', 'Autre']

@teacher_crud_bp.route('/classes/new', methods=['GET', 'POST'])
@login_required
def new_class():
    if request.method == 'POST':
        c = Classroom(teacher_id=current_user.id, name=request.form['name'].strip(),
                      subject=request.form.get('subject', '').strip() or None,
                      level=request.form.get('level', '').strip() or None,
                      school_year=request.form.get('school_year', '').strip() or _default_school_year())
        db.session.add(c); db.session.commit()
        flash(f'Classe « {c.name} » créée.', 'success')
        return redirect(url_for('teacher_crud.class_detail', class_id=c.id))
    return render_template('teacher/new_class.html', levels=CLASS_LEVELS, default_year=_default_school_year())

@teacher_crud_bp.route('/classes/<int:class_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_class(class_id):
    c = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    LEVELS = ['6ème', '5ème', '4ème', '3ème', '2nde', '1ère', 'Terminale', 'Autre']
    if request.method == 'POST':
        c.name = request.form['name'].strip(); c.subject = request.form.get('subject', '').strip()
        c.school_year = request.form.get('school_year', '2025-2026').strip(); c.level = request.form.get('level', '').strip() or None
        db.session.commit(); flash(f'Classe « {c.name} » mise à jour.', 'success')
        return redirect(url_for('teacher_crud.class_detail', class_id=c.id))
    return render_template('teacher/edit_class.html', classroom=c, levels=LEVELS)

@teacher_crud_bp.route('/classes/<int:class_id>')
@login_required
def class_detail(class_id):
    c = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    students = Student.query.filter_by(classroom_id=class_id).order_by(Student.student_number).all()
    for s in students:
        try: s.display_first = decrypt_name(s.encrypted_first_name); s.display_last = decrypt_name(s.encrypted_last_name)
        except Exception: s.display_first = s.display_last = '—'
    assignments = Assignment.query.filter_by(classroom_id=class_id).order_by(Assignment.date.desc()).all()
    total = len(students)
    ids = {s.id for s in students}
    progress = {}
    for a in assignments:
        corrected = {row[0] for row in db.session.query(Correction.student_id).filter_by(assignment_id=a.id).all()} & ids
        published = db.session.query(db.func.count(Correction.id)).filter_by(assignment_id=a.id, status='published').scalar() or 0
        progress[a.id] = {'done': len(corrected), 'total': total, 'published': published,
                          'pct': int(len(corrected) / total * 100) if total else 0}
    return render_template('teacher/class_detail.html', classroom=c, students=students,
                           assignments=assignments, progress=progress)

@teacher_crud_bp.route('/classes/<int:class_id>/students/add', methods=['POST'])
@login_required
def add_student(class_id):
    Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    first = request.form['first_name'].strip(); last = request.form['last_name'].strip()
    number = Student.query.filter_by(classroom_id=class_id).count() + 1
    s = Student(classroom_id=class_id, alias=generate_alias(first, last, number), student_number=number, encrypted_first_name=encrypt_name(first), encrypted_last_name=encrypt_name(last))
    db.session.add(s); db.session.commit()
    flash(f'Élève ajouté — alias : {s.alias}.', 'success')
    return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/classes/<int:class_id>/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(class_id, student_id):
    Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    s = Student.query.filter_by(id=student_id, classroom_id=class_id).first_or_404()
    if request.method == 'POST':
        first = request.form['first_name'].strip(); last = request.form['last_name'].strip()
        s.encrypted_first_name = encrypt_name(first); s.encrypted_last_name = encrypt_name(last)
        s.alias = generate_alias(first, last, s.student_number); db.session.commit()
        flash('Élève mis à jour.', 'success'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
    try: first = decrypt_name(s.encrypted_first_name); last = decrypt_name(s.encrypted_last_name)
    except Exception: first = last = ''
    return render_template('teacher/edit_student.html', classroom_id=class_id, student=s, first=first, last=last)

@teacher_crud_bp.route('/classes/<int:class_id>/students/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(class_id, student_id):
    Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    s = Student.query.filter_by(id=student_id, classroom_id=class_id).first_or_404()
    alias = s.alias; db.session.delete(s); db.session.commit()
    flash(f'Élève {alias} supprimé.', 'success'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/classes/<int:class_id>/delete', methods=['POST'])
@login_required
def delete_class(class_id):
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    db.session.delete(classroom); db.session.commit()
    flash(f'Classe "{classroom.name}" supprimée.', 'success'); return redirect(url_for('teacher_crud.classes'))

@teacher_crud_bp.route('/classes/<int:class_id>/import/csv', methods=['POST'])
@login_required
def import_csv_class(class_id):
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    f = request.files.get('csv_file')
    if not f: flash('Aucun fichier sélectionné.', 'danger'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
    try:
        raw = f.read()
        try: content = raw.decode('utf-8-sig')
        except UnicodeDecodeError: content = raw.decode('latin-1')
        first_line = content.split('\n')[0]
        delim = '\t' if '\t' in first_line else (';' if first_line.count(';') > first_line.count(',') else ',')
        reader = csv.DictReader(io.StringIO(content), delimiter=delim)
        rows = list(reader)
        if not rows: flash('Fichier vide.', 'danger'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
        cols = {k.strip().lower(): k for k in rows[0].keys()}
        col_nom = cols.get('nom'); col_prenom = cols.get('prénom') or cols.get('prenom')
        if not col_nom or not col_prenom: flash('Colonnes "Nom" et "Prénom" introuvables.', 'danger'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
        existing = set()
        for s in classroom.students:
            try: fn = decrypt_name(s.encrypted_first_name).strip().lower(); ln = decrypt_name(s.encrypted_last_name).strip().lower(); existing.add((ln, fn))
            except Exception: pass
        added = skipped = 0; number = Student.query.filter_by(classroom_id=class_id).count()
        for row in rows:
            last = row[col_nom].strip().strip('"'); first = row[col_prenom].strip().strip('"')
            if not last or not first: continue
            if (last.lower(), first.lower()) in existing: skipped += 1; continue
            number += 1
            db.session.add(Student(classroom_id=class_id, alias=generate_alias(first, last, number), student_number=number, encrypted_first_name=encrypt_name(first), encrypted_last_name=encrypt_name(last)))
            existing.add((last.lower(), first.lower())); added += 1
        db.session.commit(); flash(f'{added} élève(s) importé(s). {skipped} doublon(s) ignoré(s).', 'success')
    except Exception as e: current_app.logger.error(f'Import CSV error: {e}'); flash("Erreur lors de l'import.", 'danger')
    return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/import/pronote-file', methods=['POST'])
@login_required
def import_pronote_file():
    class_name = request.form.get('class_name', '').strip(); subject = request.form.get('subject', '').strip(); year = request.form.get('school_year', '2025-2026').strip()
    f = request.files.get('csv_file')
    if not class_name or not f: flash('Nom de classe et fichier requis.', 'danger'); return redirect(url_for('teacher_admin.admin'))
    try:
        raw = f.read()
        try: content = raw.decode('utf-8-sig')
        except UnicodeDecodeError: content = raw.decode('latin-1')
        reader = csv.DictReader(io.StringIO(content), delimiter=';'); rows = list(reader)
        if not rows: flash('Fichier vide.', 'danger'); return redirect(url_for('teacher_admin.admin'))
        col_eleves = None
        for k in rows[0].keys():
            if 'lève' in k.lower() or 'leve' in k.lower(): col_eleves = k; break
        if not col_eleves: col_eleves = list(rows[0].keys())[0]
        classroom = Classroom.query.filter_by(teacher_id=current_user.id, name=class_name, school_year=year).first()
        if not classroom: classroom = Classroom(teacher_id=current_user.id, name=class_name, subject=subject or None, school_year=year); db.session.add(classroom); db.session.flush()
        existing = set()
        for s in classroom.students:
            try: fn = decrypt_name(s.encrypted_first_name).strip().lower(); ln = decrypt_name(s.encrypted_last_name).strip().lower(); existing.add((ln, fn))
            except Exception: pass
        number = Student.query.filter_by(classroom_id=classroom.id).count(); added = skipped = 0
        for row in rows:
            eleve = row.get(col_eleves, '').strip().strip('"')
            if not eleve: continue
            m = re.match(r'^([A-ZÀÂÄÉÈÊÎÏÔÖÙÛÜÇ][A-ZÀÂÄÉÈÊËÎÔÖÙÛÜÇ\s\-]+?)\s+([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][a-zàâäéèêëîïôöùûüç].+)$', eleve)
            if m: last, first = m.group(1).strip(), m.group(2).strip()
            else: parts = eleve.rsplit(' ', 1); last, first = (parts[0], parts[1]) if len(parts) == 2 else (eleve, '—')
            if (last.lower(), first.lower()) in existing: skipped += 1; continue
            number += 1
            db.session.add(Student(classroom_id=classroom.id, alias=generate_alias(first, last, number), student_number=number, encrypted_first_name=encrypt_name(first), encrypted_last_name=encrypt_name(last)))
            existing.add((last.lower(), first.lower())); added += 1
        db.session.commit(); flash(f'Classe "{class_name}" : {added} élève(s) importé(s), {skipped} doublon(s) ignoré(s).', 'success')
    except Exception as e: import traceback; current_app.logger.error(traceback.format_exc()); flash('Une erreur est survenue lors de l\'import.', 'danger')
    return redirect(url_for('teacher_admin.admin'))

@teacher_crud_bp.route('/assignments/new/<int:class_id>', methods=['GET', 'POST'])
@login_required
def new_assignment(class_id):
    c = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    competences = Competence.query.filter_by(teacher_id=current_user.id).order_by(Competence.subject, Competence.domain, Competence.name).all()
    competences_by_subject = {}
    for comp in competences:
        subject = comp.subject or 'Autre'
        if subject not in competences_by_subject: competences_by_subject[subject] = []
        competences_by_subject[subject].append({'id': comp.id, 'name': comp.name, 'domain': comp.domain or ''})
    competences_by_domain_json = json.dumps(competences_by_subject, ensure_ascii=False)
    if request.method == 'POST':
        try:
            date_str = request.form.get('date', '').strip(); date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            a = Assignment(classroom_id=class_id, title=request.form.get('title', '').strip(), description=request.form.get('description', ''), date=date_val, total_points=float(request.form.get('total_points', 20)))
            db.session.add(a); db.session.flush()
            labels = request.form.getlist('q_label'); maxpts = request.form.getlist('q_max'); competence_ids = request.form.getlist('q_competence_id')
            for i, (lbl, mx, comp_id) in enumerate(zip(labels, maxpts, competence_ids)):
                if lbl.strip(): db.session.add(Question(assignment_id=a.id, label=lbl.strip(), max_points=float(mx or 1), competence_id=int(comp_id) if comp_id and comp_id.isdigit() else None, order=i))
            db.session.commit(); flash(f'Devoir « {a.title} » créé.', 'success'); return redirect(url_for('teacher_corr.assignment_corrections', assignment_id=a.id))
        except Exception as e: db.session.rollback(); current_app.logger.error(f'[new_assignment] {e}'); flash("Erreur lors de la création du devoir.", 'danger')
    return render_template('teacher/new_assignment.html', classroom=c, now=datetime.today(), competences_by_domain=competences_by_subject, competences_by_domain_json=competences_by_domain_json)

@teacher_crud_bp.route('/assignments/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_assignment(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a: abort(404)
    if a.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    if request.method == 'POST':
        a.title = request.form['title'].strip(); a.description = request.form.get('description', ''); a.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date(); a.total_points = float(request.form.get('total_points', 20))
        for q in a.questions:
            label = request.form.get(f'q_label_{q.id}', '').strip(); comp_id = request.form.get(f'q_competence_id_{q.id}', '').strip(); new_max = request.form.get(f'q_max_{q.id}'); force_clamp = request.form.get(f'q_clamp_{q.id}') == '1'
            if label: q.label = label
            q.competence_id = int(comp_id) if comp_id and comp_id.isdigit() else None
            if new_max is not None:
                new_max = float(new_max)
                if new_max != q.max_points:
                    if force_clamp:
                        from app.models import QuestionScore
                        for qs in QuestionScore.query.filter_by(question_id=q.id).all():
                            if qs.score is not None and qs.score > new_max: qs.score = new_max
                        affected = {qs.correction_id for qs in QuestionScore.query.filter_by(question_id=q.id).all()}
                        for corr in db.session.query(Assignment).get(assignment_id).corrections:
                            if corr.id in affected: corr.compute_total()
                    q.max_points = new_max
        db.session.commit(); flash('Devoir mis à jour.', 'success'); return redirect(url_for('teacher_crud.class_detail', class_id=a.classroom_id))
    questions_data = []
    for q in a.questions:
        from app.models import QuestionScore; count = QuestionScore.query.filter_by(question_id=q.id).count(); questions_data.append({'question': q, 'corrections_count': count})
    competences = Competence.query.filter_by(teacher_id=current_user.id).order_by(Competence.subject, Competence.domain, Competence.name).all()
    competences_by_subject = {}
    for comp in competences:
        subject = comp.subject or 'Autre'
        if subject not in competences_by_subject: competences_by_subject[subject] = []
        competences_by_subject[subject].append({'id': comp.id, 'name': comp.name, 'domain': comp.domain or ''})
    competences_by_domain_json = json.dumps(competences_by_subject, ensure_ascii=False)
    return render_template('teacher/edit_assignment.html', assignment=a, questions_data=questions_data, competences_by_domain_json=competences_by_domain_json)

@teacher_crud_bp.route('/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a: abort(404)
    if a.classroom.teacher_id != current_user.id: flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_crud.dashboard'))
    class_id, title = a.classroom_id, a.title; db.session.delete(a); db.session.commit()
    flash(f'Devoir « {title} » supprimé.', 'success'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/classes/<int:class_id>/add-teacher', methods=['POST'])
@login_required
def add_teacher_to_class(class_id):
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    email = request.form.get('email', '').strip().lower(); teacher = Teacher.query.filter_by(email=email).first()
    if not teacher: flash('Enseignant non trouvé.', 'danger'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
    if teacher.id == current_user.id: flash('Vous ne pouvez pas vous ajouter vous-même.', 'warning'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
    existing = ClassroomTeacher.query.filter_by(classroom_id=class_id, teacher_id=teacher.id).first()
    if existing: flash('Cet enseignant est déjà dans la classe.', 'warning')
    else: ct = ClassroomTeacher(classroom_id=class_id, teacher_id=teacher.id, role='editor'); db.session.add(ct); db.session.commit(); flash(f'{teacher.full_name} ajouté à la classe.', 'success')
    return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/classes/<int:class_id>/group/add', methods=['POST'])
@login_required
def add_group(class_id):
    classroom = db.session.get(Classroom, class_id)
    if not classroom or classroom.teacher_id != current_user.id: abort(404)
    name = request.form.get('group_name', '').strip()
    if name: group = Group(classroom_id=class_id, name=name); db.session.add(group); db.session.commit(); flash(f'Groupe "{name}" créé.', 'success')
    return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/classes/<int:class_id>/group/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(class_id, group_id):
    classroom = db.session.get(Classroom, class_id)
    if not classroom or classroom.teacher_id != current_user.id: abort(404)
    group = db.session.get(Group, group_id)
    if not group: abort(404)
    if group.classroom_id != class_id: abort(403)
    db.session.delete(group); db.session.commit(); flash('Groupe supprimé.', 'success'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))

@teacher_crud_bp.route('/classes/<int:class_id>/group/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(class_id, group_id):
    classroom = db.session.get(Classroom, class_id)
    if not classroom or classroom.teacher_id != current_user.id: abort(404)
    group = db.session.get(Group, group_id)
    if not group: abort(404)
    if group.classroom_id != class_id: abort(403)
    if request.method == 'POST':
        group.name = request.form.get('name', '').strip(); student_ids = request.form.getlist('student_ids', type=int)
        GroupStudent.query.filter_by(group_id=group_id).delete()
        for sid in student_ids: db.session.add(GroupStudent(group_id=group_id, student_id=sid))
        db.session.commit(); flash('Groupe mis à jour.', 'success'); return redirect(url_for('teacher_crud.class_detail', class_id=class_id))
    students = Student.query.filter_by(classroom_id=class_id).all()
    for s in students:
        try: s.display_first = decrypt_name(s.encrypted_first_name); s.display_last = decrypt_name(s.encrypted_last_name)
        except Exception: s.display_first = s.display_last = '—'
    members = {gs.student_id for gs in group.students}
    return render_template('teacher/edit_group.html', classroom=classroom, group=group, students=students, members=members)