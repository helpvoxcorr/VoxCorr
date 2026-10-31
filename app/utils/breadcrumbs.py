"""Fil d'Ariane : Accueil › Mes classes › 63 › DS n°1 › DUPONT Léa.
Chaque niveau est un lien et utilise le vrai nom (classe, devoir, élève)."""
from flask import request, url_for
from flask_login import current_user

BREADCRUMB_MAP = {}  # conservé pour d'éventuels anciens imports


def _student_label(student):
    from app.services.anonymization import decrypt_name
    try:
        return f"{decrypt_name(student.encrypted_last_name)} {decrypt_name(student.encrypted_first_name)}"
    except Exception:
        return student.alias


def _classroom(class_id):
    from app.extensions import db
    from app.models import Classroom
    c = db.session.get(Classroom, class_id) if class_id else None
    return c if c and c.teacher_id == current_user.id else None


def _assignment(assignment_id):
    from app.extensions import db
    from app.models import Assignment
    a = db.session.get(Assignment, assignment_id) if assignment_id else None
    return a if a and a.classroom.teacher_id == current_user.id else None


def build_breadcrumb(endpoint, context=None):
    try:
        return _build(endpoint)
    except Exception:
        return []


def _build(endpoint):
    from app.extensions import db
    from app.models import Student, Correction

    args = request.view_args or {}
    crumbs = []

    def add(label, url=None):
        crumbs.append({'label': label, 'url': url})

    def to_classes():
        add('Accueil', url_for('teacher_crud.dashboard'))
        add('Mes classes', url_for('teacher_crud.classes'))

    def to_class(c):
        to_classes()
        add(c.name, url_for('teacher_crud.class_detail', class_id=c.id))

    def to_assignment(a):
        to_class(a.classroom)
        add(a.title, url_for('teacher_corr.assignment_corrections', assignment_id=a.id))

    if endpoint == 'teacher_crud.classes':
        to_classes()
    elif endpoint == 'teacher_crud.new_class':
        to_classes(); add('Nouvelle classe')
    elif endpoint == 'teacher_crud.class_detail':
        c = _classroom(args.get('class_id'))
        if c: to_class(c)
    elif endpoint == 'teacher_crud.edit_class':
        c = _classroom(args.get('class_id'))
        if c: to_class(c); add('Modifier la classe')
    elif endpoint == 'teacher_crud.new_assignment':
        c = _classroom(args.get('class_id'))
        if c: to_class(c); add('Nouveau devoir')
    elif endpoint == 'teacher_crud.edit_assignment':
        a = _assignment(args.get('assignment_id'))
        if a: to_assignment(a); add('Modifier le devoir')
    elif endpoint == 'teacher_crud.edit_student':
        c = _classroom(args.get('class_id'))
        if c: to_class(c); add("Modifier l'élève")
    elif endpoint == 'teacher_crud.edit_group':
        c = _classroom(args.get('class_id'))
        if c: to_class(c); add('Modifier le groupe')
    elif endpoint == 'teacher_corr.assignment_corrections':
        a = _assignment(args.get('assignment_id'))
        if a: to_assignment(a)
    elif endpoint == 'teacher_corr.print_corrections':
        a = _assignment(args.get('assignment_id'))
        if a: to_assignment(a); add('Impression')
    elif endpoint == 'teacher_corr.record':
        a = _assignment(args.get('assignment_id'))
        s = db.session.get(Student, args.get('student_id')) if args.get('student_id') else None
        if a and s and s.classroom_id == a.classroom_id:
            to_assignment(a); add(_student_label(s))
    elif endpoint == 'teacher_corr.correction_detail':
        corr = db.session.get(Correction, args.get('correction_id'))
        a = _assignment(corr.assignment_id) if corr else None
        if a:
            to_assignment(a); add(_student_label(corr.student))
    elif endpoint == 'teacher_corr.list_competences':
        add('Accueil', url_for('teacher_crud.dashboard')); add('Compétences')
    elif endpoint == 'teacher_admin.admin':
        add('Accueil', url_for('teacher_crud.dashboard')); add('Paramètres')
    elif endpoint == 'teacher_admin.access_codes':
        add('Accueil', url_for('teacher_crud.dashboard'))
        add('Paramètres', url_for('teacher_admin.admin')); add("Codes d'accès")

    if crumbs:
        crumbs[-1]['url'] = None   # la page courante n'est pas un lien
    return crumbs