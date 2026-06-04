import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import Student, Pupil

app, _ = create_app()

with app.app_context():
    for student in Student.query.all():
        existing = Pupil.query.filter_by(student_id=student.id).first()
        if not existing:
            code = Pupil.generate_access_code()
            pupil = Pupil(student_id=student.id, access_code=code)
            db.session.add(pupil)
            print(f"Code généré pour {student.alias} : {code}")
    db.session.commit()
    print("Terminé.")