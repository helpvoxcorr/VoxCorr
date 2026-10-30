# VOXCORR — Prompt permanent pour agent IA

## C'est quoi
App web Flask. Prof dicte correction orale. IA transcrit + structure + extrait notes. QR code envoyé à élève. Élève lit/écoute sans compte.

## Stack
- Backend : Flask 3 + SQLAlchemy + Flask-Login + Flask-Migrate + Flask-WTF (CSRF) + Flask-Limiter
- DB : PostgreSQL (Neon prod) / SQLite (dev local)
- Audio : Cloudinary (resource_type='video', converti .mp3)
- IA : Mistral AI (`mistral-small-latest` synthèse, `voxtral-mini-latest` transcription)
- TTS : Edge TTS (gratuit, voix `fr-FR-DeniseNeural`)
- Email : SendGrid (HTTP direct via urllib)
- Front : Bootstrap 5.3.3 + Bootstrap Icons + police Inter + Wavesurfer.js + Plotly
- PWA : Service Worker + manifest.json
- Hébergement : Render.com (tier gratuit)

## Flux utilisateur

### Prof
1. Login → Dashboard → Créer classe → Ajouter élèves (ou import CSV Pronote)
2. Créer devoir (titre, date, total points, questions avec barème + compétence)
3. Page corrections → Cliquer "Corriger" sur élève → Page `record.html`
4. Cliquer micro vert → Dicter correction (mentionner notes : "Question 1, 3,5 sur 5")
5. Cliquer stop → Sauvegarder → IA Mistral analyse (thread daemon)
6. Vérifier notes extraites → Publier → QR code généré
7. Télécharger QR PNG ou imprimer page corrections

### Élève
- **Via QR code** : Scan → Page publique `/c/<token>` → Lit synthèse + écoute audio + télécharge hors-ligne
- **Via code accès** : Login `/student/login` avec code 8 caractères → Dashboard → Détail correction

## Architecture dossiers
/app
init.py # create_app(), enregistre blueprints, error handlers, breadcrumb
config.py # Config class, lit .env (SECRET_KEY, DB, Cloudinary, Mistral, SendGrid, ENCRYPTION_KEY)
extensions.py # db, migrate, login_manager, csrf, limiter, socketio
/blueprints
auth.py # /auth/login, /auth/register, /auth/verify/<token>, /auth/logout
public.py # /c/<token> (page élève publique), /c/<token>/read
pages.py # /pages/documentation, /pages/aide, /pages/mentions-legales, /pages/rgpd, /pages/contact, /pages/licence
student.py # /student/login, /student/dashboard, /student/correction/<id>, /student/api/tts/<id>
teacher_crud.py # /teacher/dashboard, /teacher/classes, CRUD classes/élèves/devoirs/groupes, import CSV Pronote
teacher_corrections.py # /teacher/assignments/<id>/corrections, /teacher/record/<sid>/<aid>, API save/status/publish/audio/resynthesize, PDF, TTS
teacher_admin.py # /teacher/admin (verrouillé par mot de passe), thème, export notes, import compétences, reset année, suppression compte
teacher_stats.py # /teacher/api/stats/class/<id>, /teacher/api/stats/level/<level>, /teacher/api/student/<id>/competence-stats, /prediction
/models
init.py # Teacher, Classroom, Student, Pupil, Assignment, Question, Correction, QuestionScore, Competence, CompetenceScore, AccessLog, ClassroomTeacher, Group, GroupStudent
/services
ai.py # synthesize_with_mistral() (Mistral → JSON {formatted_text, grades}), synthesize_appreciation(), transcribe_with_mistral() (Voxtral), normalize_transcript()
anonymization.py # encrypt_name(), decrypt_name() (Fernet AES-128), generate_alias() (Animal-NN déterministe)
background.py # run_in_background() (threading.Thread daemon, évite Celery sur Render Free)
email.py # send_verification_email() (SendGrid HTTP direct)
qrcode.py # make_qr() (base64 PNG), qr_png_bytes()
storage.py # upload_audio() (Cloudinary), delete_audio()
tts.py # generate_tts_audio() (Edge TTS → bytes MP3)
/static
/css # voxcorr.css (ancien design system), tokens.css + base.css + components.css + errors.css + auth.css (nouveau design system en migration)
/js # recorder.js (VoxRecorder class, Web Speech API + MediaRecorder), record_page.js (orchestrateur page record), record_inline.js (version inline), audio_editor.js (WaveSurfer), sw.js (Service Worker)
# /js/modules/api.js (fetch centralisés), /js/modules/ui.js (machine à états)
/icons # icon.svg, icon-maskable.svg, icon-192x192.png, icon-512x512.png
manifest.json # PWA manifest
/templates
base.html # Layout principal, navbar, breadcrumb, flash messages
/auth # login.html, register.html
/components # modals.html (VoxModal.confirm/alert/loading)
/errors # 403.html, 404.html, 429.html, 500.html
/pages # documentation.html, aide.html, mentions_legales.html, rgpd.html, contact.html, licence.html
/public # student.html (page élève publique via QR)
/student # login.html, dashboard.html, correction.html (espace élève connecté)
/teacher # dashboard.html, classes.html, class_detail.html, new_class.html, edit_class.html, new_assignment.html, edit_assignment.html, assignment_corrections.html, record.html, correction_detail.html, print_corrections.html, correction_pdf.html, edit_student.html, edit_group.html, admin.html, competences.html
/utils
breadcrumbs.py # BREADCRUMB_MAP + build_breadcrumb()
security.py # hash_password(), verify_password(), generate_token(), token_required() (JWT, non utilisé actuellement), hash_ip() (HMAC-SHA256)
/ (racine)
run.py # Point d'entrée dev (flask run)
server.py # Point d'entrée prod (gunicorn)
requirements.txt # Dépendances Python
render.yaml # Config déploiement Render
start_ngrok.bat # Tunnel ngrok pour dev local
generate_access_codes.py # Script génération codes accès élèves
seed_competences.py # Script seed compétences socle
AUDIT_VOXCORR_2026.md # Audit complet (bugs, duplications, plan action)


## Modèles de données clés

- **Teacher** : email, password_hash, email_verified, theme_primary/secondary/bg
- **Classroom** : name, subject, school_year, level → teacher_id
- **Student** : alias (Animal-NN), student_number, encrypted_first_name, encrypted_last_name → classroom_id
- **Pupil** : access_code (8 chars) → student_id (1-to-1)
- **Assignment** : title, description, date, total_points, class_appreciation, public_token → classroom_id
- **Question** : label, max_points, order, competence_id → assignment_id
- **Correction** : public_token, raw_transcript, structured_text, audio_url, audio_duration, total_score, status (draft/processing/published), published_at, read_at → student_id + assignment_id
- **QuestionScore** : score, advice → correction_id + question_id
- **Competence** : name, domain (D1-D5), subject, teacher_id (NULL = socle commun)
- **AccessLog** : ip_hash, user_agent, accessed_at → correction_id

## Services IA (ai.py)

### synthesize_with_mistral()
- Entrée : raw_transcript, question_labels, question_max
- Appel Mistral API (`mistral-small-latest`) avec SYSTEM_PROMPT détaillé
- Retourne JSON : `{formatted_text: "<p>HTML...</p>", grades: [{question_index, score, max_score, competence, advice}]}`
- Fallback regex si API échoue

### synthesize_appreciation()
- Reformule appréciation générale dictée oralement
- Même pattern Mistral → JSON `{formatted_text: "..."}`

### transcribe_with_mistral()
- Transcription audio via Voxtral (`voxtral-mini-latest`)
- Fallback pour navigateurs sans Web Speech API (Firefox)

## Points d'attention

### Bugs identifiés (audit juin 2026)
1. **Lien mort** : `teacher_crud.import_pronote_file` redirige vers `url_for('teacher_crud.admin')` → route inexistante. Devrait être `teacher_admin.admin`
2. **Pages légales tronquées** : `licence.html` et `mentions_legales.html` incomplètes sur disque
3. **edit_group.html** : noms non déchiffrés (`s.display_last`/`s.display_first` non calculés dans route)
4. **Pages élève non stylées** : `student/dashboard.html` et `student/correction.html` utilisent classes CSS absentes de `voxcorr.css`

### Duplications
- Pattern autorisation écrit 3 façons différentes → candidat pour décorateur `@require_classroom_owner`
- Import CSV élèves dupliqué entre `import_csv_class` et `import_pronote_file`
- Modales suppression JS ad hoc dans `classes.html` et `dashboard.html` → devrait utiliser `components/modals.html` (VoxModal)
- FAQ dupliquée entre `aide.html` et `documentation.html`

### Conventions CSS
- 3 systèmes coexistent : `vox-*` (principal), `ac-*`/`cd-*`/`dash-*`/`rec-*` (page-spécifiques), + classes non rattachées (student dashboard/correction)
- Collision préfixe `cd-` : utilisé pour Class Detail ET Correction Detail + Record
- Migration en cours vers nouveau design system (tokens.css + base.css + components.css)

### Sécurité
- Noms élèves chiffrés Fernet (AES-128) avec clé `ENCRYPTION_KEY`
- Alias déterministe (Animal-NN) pour anonymisation
- IP logs hashées HMAC-SHA256 avec `SECRET_KEY`
- CSRF protection Flask-WTF
- Rate limiting Flask-Limiter (10/min login, 5/h register, etc.)
- Session admin verrouillée par mot de passe + expiration 30min

### Performance
- Thread daemon pour tâches IA (évite Celery sur Render Free tier)
- Audio uploadé Cloudinary après sauvegarde correction (non-bloquant)
- Polling JS toutes les 2s pour statut correction (pas de WebSocket)
- Service Worker cache statiques, exclut API + audio

## Variables d'environnement requises (.env)
SECRET_KEY=...
DATABASE_URL=postgresql://... (ou sqlite:///voxcorr_dev.db)
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
MISTRAL_API_KEY=...
ENCRYPTION_KEY=... (Fernet key, 32 chars base64)
APP_BASE_URL=https://... (URL publique pour QR codes)
SENDGRID_API_KEY=...
SENDGRID_FROM_EMAIL=help.voxcorr@gmail.com
SENDGRID_FROM_NAME=VoxCorr Team


## Commandes utiles

```bash
# Dev local
python run.py

# Migrations
flask db migrate -m "description"
flask db upgrade

# Génération codes accès élèves
python generate_access_codes.py

# Seed compétences socle
python seed_competences.py

# Tunnel ngrok (dev)
start_ngrok.bat

Conventions code
Blueprints préfixes : /auth, /student, /teacher, /pages, /c/<token> (public)
Templates Jinja2 héritent tous de base.html
Fetch JS centralisés dans api.js (aucun fetch() ailleurs)
Machine à états UI dans ui.js (idle → recording → stopped → processing → done → published)
Breadcrumb dynamique via breadcrumbs.py + context processor inject_breadcrumb()
Thème dynamique injecté via current_user.theme_primary/secondary/bg dans base.html