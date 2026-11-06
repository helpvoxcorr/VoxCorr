import csv
import io
import re
from datetime import date, datetime

from flask import Blueprint, render_template, send_file
from flask_login import login_required, current_user

from app.models import Classroom, Student, Correction
from app.services.anonymization import decrypt_name
from app.services import suivi

teacher_suivi_bp = Blueprint('teacher_suivi', __name__, url_prefix='/teacher')


def _names(s):
    try:
        return decrypt_name(s.encrypted_last_name), decrypt_name(s.encrypted_first_name)
    except Exception:
        return s.alias, ''


def _own_class(class_id):
    return Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()


def _adate(a):
    return a.date or (a.created_at.date() if a.created_at else date.min)


def _csv_safe(value):
    value = '' if value is None else str(value)
    return ('\t' + value) if value.startswith(('=', '+', '-', '@')) else value


@teacher_suivi_bp.route('/classes/<int:class_id>/students/<int:student_id>')
@login_required
def student_sheet(class_id, student_id):
    classroom = _own_class(class_id)
    student = Student.query.filter_by(id=student_id, classroom_id=class_id).first_or_404()
    last, first = _names(student)
    domains = suivi.by_domain(suivi.student_summary(student.id))

    ordered = Student.query.filter_by(classroom_id=class_id).order_by(Student.student_number).all()
    i = [s.id for s in ordered].index(student.id)
    prev_s = ordered[i - 1] if i > 0 else None
    next_s = ordered[i + 1] if i < len(ordered) - 1 else None

    corrs = {c.assignment_id: c for c in Correction.query.filter_by(student_id=student.id).all()}
    devoirs = [{'assignment': a, 'correction': corrs.get(a.id)}
               for a in sorted(classroom.assignments, key=_adate, reverse=True)]
    return render_template('teacher/student_sheet.html', classroom=classroom, student=student,
                           last=last, first=first, domains=domains, devoirs=devoirs, legend=suivi.legend(),
                           prev_s=prev_s, prev_name=' '.join(_names(prev_s)) if prev_s else '',
                           next_s=next_s, next_name=' '.join(_names(next_s)) if next_s else '')


@teacher_suivi_bp.route('/classes/<int:class_id>/competences')
@login_required
def class_matrix(class_id):
    classroom = _own_class(class_id)
    students = Student.query.filter_by(classroom_id=class_id).order_by(Student.student_number).all()
    columns, cells = suivi.class_matrix([s.id for s in students])
    rows = [{'student': s, 'last': _names(s)[0], 'first': _names(s)[1]} for s in students]
    rows.sort(key=lambda r: (r['last'].lower(), r['first'].lower()))
    return render_template('teacher/class_competences.html', classroom=classroom, rows=rows,
                           columns=columns, cells=cells, legend=suivi.legend())


@teacher_suivi_bp.route('/classes/<int:class_id>/competences.csv')
@login_required
def class_matrix_csv(class_id):
    classroom = _own_class(class_id)
    students = Student.query.filter_by(classroom_id=class_id).order_by(Student.student_number).all()
    columns, cells = suivi.class_matrix([s.id for s in students])
    rows = sorted(((_names(s), s) for s in students), key=lambda t: (t[0][0].lower(), t[0][1].lower()))

    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    head = ['Nom', 'Prénom']
    for col in columns:
        head += [f"{col['name']} — moyenne /4", f"{col['name']} — palier (1 à 4)", f"{col['name']} — évaluations"]
    w.writerow([_csv_safe(h) for h in head])
    for (last, first), s in rows:
        line = [_csv_safe(last), _csv_safe(first)]
        for col in columns:
            g = cells[s.id].get(col['id'])
            if g:
                sm = g['summary']
                line += [str(sm['on4']).replace('.', ','), sm['level']['rank'], sm['count']]
            else:
                line += ['', '', '']
        w.writerow(line)
    slug = re.sub(r'[^A-Za-z0-9_-]+', '', classroom.name) or 'classe'
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True,
                     download_name=f'competences_{slug}_{datetime.now().strftime("%Y%m%d")}.csv')