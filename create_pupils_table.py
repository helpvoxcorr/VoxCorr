import os
import sys

# Ajoute le chemin du projet pour pouvoir importer les modules
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import Pupil  # force l'import du modèle

app, _ = create_app()

with app.app_context():
    # Crée la table pupils si elle n'existe pas
    db.create_all()
    print("Table 'pupils' créée (ou déjà existante).")