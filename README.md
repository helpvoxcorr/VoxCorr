# VoxCorr – Correction audio assistée par IA

VoxCorr est une application web Flask permettant aux enseignants d’enregistrer des corrections orales de copies. L’audio est stocké sur Cloudinary, la transcription est structurée par l’IA Mistral, et chaque élève reçoit un QR code pour accéder à sa correction sans compte.

## Fonctionnalités

- Enregistrement audio (micro navigateur) et transcription automatique
- Synthèse IA (Mistral) des commentaires avec extraction des notes
- Génération de QR codes pour consultation sans compte
- Portail élève sécurisé par code d’accès
- Éditeur audio (waveform, lecture/pause/zoom)
- Statistiques de progression par classe (graphiques Plotly)
- Conseils personnalisés par compétence
- Synthèse vocale (TTS) des corrections
- Export CSV des notes (pour Pronote, Moodle…)
- Purge automatique des logs et brouillons
- Protection CSRF, limit rate, session admin sécurisée
- PWA (Service Worker, cache statique, hors-ligne partiel)

## Stack technique

- Backend : Flask 3, SQLAlchemy, Flask-Login, Flask-Migrate, Flask-WTF, Flask-Limiter
- Base de données : PostgreSQL (Neon) ou SQLite
- Stockage audio : Cloudinary
- IA : Mistral AI (mistral-small-latest)
- TTS : Edge TTS (Microsoft, gratuit)
- Frontend : Bootstrap 5, Wavesurfer.js, Plotly
- PWA : Service Worker, manifest.json
- Hébergement : Render (ou local)

## Installation (développement)

1. Cloner le dépôt :
   ```bash
   git clone https://github.com/votre-utilisateur/voxcorr.git
   cd voxcorr