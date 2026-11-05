"""Prépare la base de développement locale (SQLite).
À lancer une fois : python dev_setup.py  (relançable sans risque)."""
import os
import sys
from datetime import date

os.environ['VOXCORR_ENV'] = 'dev'

from app import create_app
from app.extensions import db
from app.models import Teacher, Classroom, Student, Pupil, Assignment, Question, Competence
from app.services.anonymization import generate_alias, encrypt_name

app, _ = create_app()

with app.app_context():
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        sys.exit("Arrêt : la base n'est pas SQLite.")
    db.create_all()

    email = os.environ.get('ADMIN_EMAIL', 'admin@voxcorr.test').strip().lower()
    password = os.environ.get('DEV_ADMIN_PASSWORD')
    if not password:
        sys.exit('DEV_ADMIN_PASSWORD manque dans .env.dev')

    teacher = Teacher.query.filter_by(email=email).first()
    if not teacher:
        teacher = Teacher(email=email, first_name='Admin', last_name='Dev', school='Collège de test')
        teacher.set_password(password)
        teacher.email_verified = True
        db.session.add(teacher)
        db.session.commit()
        print(f'Compte créé : {email}')

    if not Classroom.query.filter_by(teacher_id=teacher.id, name='6e Test').first():
        classroom = Classroom(teacher_id=teacher.id, name='6e Test', level='6ème',
                              subject='SVT', school_year='2026-2027')
        db.session.add(classroom)
        db.session.flush()

        eleves = [('Alice', 'Martin'), ('Bastien', 'Durand'), ('Camille', 'Lefèvre'),
                  ('Dylan', 'Moreau'), ('Emma', 'Garnier'), ('Farid', 'Haddad')]
        for i, (first, last) in enumerate(eleves, 1):
            s = Student(classroom_id=classroom.id, alias=generate_alias(first, last, i), student_number=i,
                        encrypted_first_name=encrypt_name(first), encrypted_last_name=encrypt_name(last))
            db.session.add(s)
            db.session.flush()
            db.session.add(Pupil(student_id=s.id, access_code=Pupil.generate_access_code()))

        langages = Competence(name='Pratiquer des langages', domain='D1', subject='SVT', teacher_id=teacher.id)
        demarches = Competence(name='Pratiquer des démarches scientifiques', domain='D4', subject='SVT', teacher_id=teacher.id)
        documents = Competence(name='Tirer des informations d\'un document', domain='D2', subject='SVT', teacher_id=teacher.id)
        db.session.add_all([langages, demarches, documents])
        db.session.flush()

        devoir = Assignment(classroom_id=classroom.id, title="DS d'essai : le cycle de l'eau",
                            date=date.today(), total_points=20.0)
        db.session.add(devoir)
        db.session.flush()
        for ordre, (label, points, comp) in enumerate([
            ("Définir le cycle de l'eau", 4.0, langages),
            ('Classer les états de l\'eau', 6.0, demarches),
            ("Tirer des informations d'un document", 10.0, documents),
        ]):
            db.session.add(Question(assignment_id=devoir.id, label=label, max_points=points,
                                    competence_id=comp.id, order=ordre))
        db.session.commit()
        print('Classe « 6e Test » créée : 6 élèves, 3 compétences, 1 devoir de 20 points.')

    exemple = Pupil.query.first()
    print(f'\nConnexion : {email}  /  mot de passe : {password}')
    if exemple:
        print(f"Exemple de code d'accès élève : {exemple.access_code}")
    print('Lancer ensuite : python run_dev.py')