from app import create_app, db
from app.models import Competence

app, _ = create_app()
with app.app_context():
    for name in ["Rédaction", "Orthographe", "Grammaire", "Calcul", "Raisonnement", "Analyse", "Synthèse"]:
        if not Competence.query.filter_by(name=name).first():
            db.session.add(Competence(name=name))
    db.session.commit()
    print("Compétences ajoutées")