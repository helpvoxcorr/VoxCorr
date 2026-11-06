"""Notes d'exemple pour tester le suivi des compétences. Base de développement (SQLite) uniquement.
Prérequis : python dev_setup.py. Relançable sans risque."""
import os
import sys
from datetime import date, timedelta

os.environ['VOXCORR_ENV'] = 'dev'

from app import create_app
from app.extensions import db
from app.models import Assignment, Classroom, Competence, Correction, Question, QuestionScore, Student

app, _ = create_app()

# devoir -> {n° d'élève : notes de Q1, Q2, Q3}
SCORES = {
    0: {1: (4, 6, 10), 2: (3, 5, 8), 3: (3, 4, 6), 4: (2, 3, 4), 5: (0, 2, 5), 6: (4, 5, 8)},
    1: {1: (2, 5, 3), 2: (2, 4, 2), 3: (1, 3, 2), 4: (1, 2, 1), 5: (0, 1, 1)},     # n° 6 : absent
    2: {1: (4, 6, 10), 2: (4, 5, 7), 3: (3, 4, 7), 4: (1, 3, 4), 5: (0, 0, 3)},    # n° 6 : pas encore corrigé
}

with app.app_context():
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        sys.exit("Arrêt : la base n'est pas SQLite.")
    classroom = Classroom.query.filter_by(name='6e Test').first()
    if not classroom:
        sys.exit("Lancez d'abord : python dev_setup.py")

    comps = {c.name: c for c in Competence.query.filter_by(teacher_id=classroom.teacher_id).all()}
    L = comps['Pratiquer des langages']
    D = comps['Pratiquer des démarches scientifiques']
    X = comps["Tirer des informations d'un document"]
    students = {s.student_number: s for s in Student.query.filter_by(classroom_id=classroom.id).all()}
    today = date.today()

    def devoir(title, days_ago, total, questions):
        a = Assignment.query.filter_by(classroom_id=classroom.id, title=title).first()
        if a:
            return a
        a = Assignment(classroom_id=classroom.id, title=title, date=today - timedelta(days=days_ago), total_points=total)
        db.session.add(a)
        db.session.flush()
        for order, (label, pts, comp) in enumerate(questions):
            db.session.add(Question(assignment_id=a.id, label=label, max_points=pts, competence_id=comp.id, order=order))
        db.session.flush()
        return a

    d1 = Assignment.query.filter_by(classroom_id=classroom.id).order_by(Assignment.id).first()
    d1.date = today - timedelta(days=28)
    d2 = devoir('DS 2 : les états de l\'eau', 14, 10.0,
                [('Vocabulaire', 2.0, L), ('Lire un document', 5.0, X), ('Mener une expérience', 3.0, D)])
    d3 = devoir('DS 3 : bilan', 0, 20.0,
                [('Lire un tableau', 4.0, X), ('Rédiger une conclusion', 6.0, L), ('Raisonner', 10.0, D)])

    for i, a in enumerate([d1, d2, d3]):
        questions = Question.query.filter_by(assignment_id=a.id).order_by(Question.order).all()
        for n, notes in SCORES[i].items():
            s = students[n]
            if Correction.query.filter_by(student_id=s.id, assignment_id=a.id).first():
                continue
            c = Correction(student_id=s.id, assignment_id=a.id, status='draft',
                           raw_transcript="Dictée d'exemple",
                           structured_text='<section data-qi="intro"><p>Résultats d\'exemple.</p></section>')
            db.session.add(c)
            db.session.flush()
            for q, note in zip(questions, notes):
                db.session.add(QuestionScore(correction_id=c.id, question_id=q.id, score=float(note)))
            db.session.flush()
            c.compute_total()
            c.publish()
    absent = students[6]
    if not Correction.query.filter_by(student_id=absent.id, assignment_id=d2.id).first():
        db.session.add(Correction(student_id=absent.id, assignment_id=d2.id, status='absent'))
    db.session.commit()
    print('Notes d\'exemple créées : 3 devoirs, 6 élèves (un absent au DS 2, un non corrigé au DS 3).')