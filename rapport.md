VoxCorr – Rapport fonctionnel et technique détaillé (version intégrale)
Ce document décrit chaque fonctionnalité avec ses fichiers, routes, flux de données, et points de vigilance.

Table des matières
Infrastructure et outils
1.1. Stack technique
1.2. Variables d’environnement
1.3. Structure des dossiers
1.4. Code mort et redondances

Module d’authentification (blueprints/auth.py)
2.1. Inscription
2.2. Connexion
2.3. Vérification email
2.4. Déconnexion

Module enseignant (blueprints/teacher.py)
3.1. Dashboard
3.2. Gestion des classes
3.3. Gestion des élèves (CRUD + import CSV)
3.4. Gestion des devoirs
3.5. Corrections d’un devoir (vue liste)
3.6. Enregistrement d’une correction (page record.html)
3.7. API JSON pour corrections
3.8. Détail d’une correction (correction_detail.html)
3.9. Appréciation générale de la classe
3.10. Impression / export
3.11. Administration (admin.html)

Module public élève (blueprints/public.py)
4.1. Visualisation d’une correction (/c/<token>)
4.2. Confirmation de lecture (/c/<token>/read)

Module pages statiques (blueprints/pages.py)

Modèles de données (models/__init__.py)

Services métier (services/)
7.1. ai.py – Mistral
7.2. anonymization.py – Alias et chiffrement
7.3. background.py – Tâches asynchrones
7.4. email.py – SendGrid
7.5. qrcode.py – QR codes
7.6. storage.py – Cloudinary

Frontend statique (static/)
8.1. CSS – voxcorr.css
8.2. JavaScript
8.2.1. recorder.js – Web Speech + MediaRecorder
8.2.2. record_page.js – Orchestrateur (module)
8.2.3. modules/api.js et modules/ui.js
8.2.4. sw.js – Service worker
8.3. manifest.json – PWA

Templates (templates/)
9.1. base.html – Layout commun
9.2. components/modals.html – Boîtes de dialogue
9.3. Templates d’erreur
9.4. Templates d’authentification
9.5. Templates des pages statiques
9.6. Templates enseignant (détail ci‑dessous)
9.7. Template élève (public/student.html)

Fonctionnalités manquantes (priorisées)

Annexe – Liste complète des routes

1. Infrastructure et outils
1.1 Stack technique
Catégorie	Composants
Langage	Python 3.13
Framework web	Flask 3.1.3 (avec blueprints)
Base de données	PostgreSQL via Neon, SQLAlchemy 2.0.49 (ORM)
Migrations	Flask-Migrate (Alembic 1.18.4)
Authentification	Flask-Login 0.6.3 (sessions)
Sécurité	Flask-WTF (CSRF), Flask-Limiter (rate limiting), Fernet (cryptographie)
IA	Mistral AI (SDK mistralai 1.7.0) – modèle mistral-small-latest
Stockage audio	Cloudinary (SDK cloudinary 1.44.2)
Emails	SendGrid (API REST directe)
QR codes	qrcode + Pillow (image stylisée)
Frontend	Bootstrap 5.3.3 (CSS/JS), Bootstrap Icons, JS vanille ES6, CSS personnalisé
PWA	Service worker (sw.js), manifeste (manifest.json)
Déploiement	Render (Gunicorn 23.0.0) – Procfile, render.yaml
1.2 Variables d’environnement (.env)
Variable	Rôle	Utilisée dans
SECRET_KEY	Sessions Flask, hash IP	app/__init__.py, utils/security.py
DATABASE_URL	Connexion PostgreSQL	app/config.py
CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET	Upload audio	services/storage.py
MISTRAL_API_KEY	Synthèse IA	services/ai.py
ENCRYPTION_KEY	Fernet – chiffrement des noms élèves	services/anonymization.py
APP_BASE_URL	URL publique (QR codes, emails)	services/qrcode.py, services/email.py
SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME	Envoi email	services/email.py
1.3 Structure des dossiers (avec précision)
text
E:\Xav-Projets\VoxCorr\
├── app/
│   ├── __init__.py              # Factory create_app, extensions, purge auto
│   ├── config.py                # Charge les variables d’environnement
│   ├── extensions.py            # Initialise db, migrate, login_manager, csrf, limiter
│   ├── models/
│   │   └── __init__.py          # 7 classes SQLAlchemy
│   ├── blueprints/
│   │   ├── auth.py              # /auth/*
│   │   ├── teacher.py           # /teacher/*
│   │   ├── public.py            # /c/*
│   │   └── pages.py             # /pages/*
│   ├── services/
│   │   ├── ai.py                # Mistral (synthesize_with_mistral, synthesize_appreciation)
│   │   ├── anonymization.py     # generate_alias, encrypt_name, decrypt_name
│   │   ├── background.py        # run_in_background (threading)
│   │   ├── email.py             # send_verification_email
│   │   ├── qrcode.py            # make_qr, qr_png_bytes
│   │   └── storage.py           # upload_audio, delete_audio
│   ├── utils/ (partiellement obsolète)
│   │   ├── ai.py                # ❌ NON UTILISÉ (Groq)
│   │   ├── security.py          # hash_ip (utilisé) + JWT (inutilisé)
│   │   └── storage.py           # ❌ DOUBLON
│   ├── static/
│   │   ├── css/voxcorr.css
│   │   ├── js/
│   │   │   ├── recorder.js
│   │   │   ├── record_page.js
│   │   │   ├── record_inline.js (obsolète)
│   │   │   ├── modules/
│   │   │   │   ├── api.js
│   │   │   │   └── ui.js
│   │   │   └── sw.js
│   │   └── manifest.json
│   └── templates/
│       ├── base.html
│       ├── components/modals.html
│       ├── errors/*.html
│       ├── auth/*.html
│       ├── pages/*.html
│       ├── public/student.html
│       └── teacher/*.html (12 templates)
├── migrations/                  # Géré par Flask-Migrate
├── requirements.txt
├── run.py                       # Point d’entrée développement
├── server.py                    # Point d’entrée production (Gunicorn)
├── Procfile, render.yaml
└── .env
1.4 Code mort / redondant – actions recommandées
Fichier	État	Action
app/utils/ai.py	Non importé nulle part	Supprimer
app/utils/storage.py	Non utilisé (services.storage est la référence)	Supprimer
app/utils/security.py	La fonction hash_ip est utilisée dans public.py. Les fonctions JWT (generate_token, token_required) ne sont jamais appelées.	Conserver uniquement hash_ip (la déplacer éventuellement dans services/anonymization.py)
app/static/js/record_inline.js	Non référencé dans record.html (c’est record_page.js qui est chargé)	Supprimer après vérification
2. Module d’authentification (blueprints/auth.py)
Préfixe URL : /auth
Blueprints : auth_bp
Dépendances : Teacher modèle, send_verification_email, limiter

2.1 Inscription – GET /auth/register, POST /auth/register
Rate limiting : 5 requêtes par heure.

Champs : prénom, nom, email, école (optionnel), mot de passe (avec force), confirmation.

Validation mot de passe : 10 caractères minimum, au moins une majuscule, une minuscule, un chiffre, un caractère spécial.

Contrôle doublon : l’email doit être unique.

Création : Teacher avec email_verified=False, verification_token généré.

Envoi email : lien {APP_BASE_URL}/auth/verify/{token} via SendGrid.

Si l’envoi échoue, le compte est supprimé et l’utilisateur est invité à réessayer.

Templates : templates/auth/register.html (inclut barre de force du mot de passe, affichage/masquage).

Fichiers clés :
auth.py (lignes 39–100), templates/auth/register.html, services/email.py

2.2 Connexion – GET /auth/login, POST /auth/login
Rate limiting : 10/min, 50/heure.

Vérification : email + mot de passe.

Email non vérifié : message d’avertissement, pas de connexion.

Remember me : optionnelle (transmise à login_user).

Redirection : next ou dashboard.

Templates : templates/auth/login.html.

Fichiers clés : auth.py (lignes 18–37)

2.3 Vérification email – GET /auth/verify/<token>
Recherche du Teacher par verification_token.

Si trouvé : email_verified = True, token supprimé, connexion automatique.

Sinon : message d’erreur.

Fichiers clés : auth.py (lignes 102–111)

2.4 Déconnexion – GET /auth/logout
Appelle logout_user().

Redirige vers /auth/login.

Fichiers clés : auth.py (lignes 113–116)

3. Module enseignant (blueprints/teacher.py)
Préfixe URL : /teacher
Blueprints : teacher_bp
Protection : @login_required sur toutes les routes (sauf explicitement noté).

3.1 Dashboard – GET /teacher/dashboard
Affiche toutes les classes de l’enseignant, groupées par discipline (maths, français, etc.).

Statistiques : nombre total d’élèves, nombre total de devoirs.

Template : teacher/dashboard.html

3.2 Gestion des classes
Route	Méthode	Description	Template
/teacher/classes	GET	Liste toutes les classes (cartes).	teacher/classes.html
/teacher/classes/new	GET, POST	Création d’une classe.	teacher/new_class.html
/teacher/classes/<int:class_id>	GET	Détail d’une classe (élèves + devoirs).	teacher/class_detail.html
/teacher/classes/<int:class_id>/delete	POST	Suppression de la classe (cascade).	–
3.3 Gestion des élèves
Route	Méthode	Description
/teacher/classes/<int:class_id>/students/add	POST	Ajout d’un élève (alias généré automatiquement).
/teacher/classes/<int:class_id>/students/<int:student_id>/edit	GET, POST	Modification prénom/nom → alias recalculé.
/teacher/classes/<int:class_id>/students/<int:student_id>/delete	POST	Suppression.
/teacher/classes/<int:class_id>/import/csv	POST	Import CSV Pronote (pour une classe existante).
/teacher/import/pronote-file	POST	Import global (création ou mise à jour d’une classe).
Détails techniques :

Les prénoms et noms sont chiffrés via Fernet (AES-128) avant stockage.

Alias généré par generate_alias(first, last, student_number) : Animal-XX.

L’import Pronote attend un CSV avec colonnes Nom, Prénom ou le format spécifique Pronote (une colonne Élèves avec NOM Prénom).

3.4 Gestion des devoirs
Route	Méthode	Description	Template
/teacher/assignments/new/<int:class_id>	GET, POST	Création d’un devoir avec questions et barème.	teacher/new_assignment.html
/teacher/assignments/<int:assignment_id>/edit	GET, POST	Édition du devoir (hors questions).	teacher/edit_assignment.html
/teacher/assignments/<int:assignment_id>/delete	POST	Suppression du devoir (cascade).	–
3.5 Corrections d’un devoir (vue liste) – GET /teacher/assignments/<int:assignment_id>/corrections
Affiche tous les élèves de la classe, avec leur correction existante (statut, note, date de lecture) ou un bouton Corriger.

Fonctionnalités supplémentaires sur cette page :

Appréciation générale de la classe (module dédié ci‑dessous).

Barre de suppression groupée (checkboxes + confirmation mot de passe).

Statistiques (modal avec histogramme et radar) – utilisent Chart.js.

Template : teacher/assignment_corrections.html

3.6 Enregistrement d’une correction (page record.html)
Route : GET /teacher/record/<int:student_id>/<int:assignment_id>

Template : teacher/record.html
JavaScript associé :

recorder.js (classe VoxRecorder)

record_page.js (module ES6)

modules/api.js, modules/ui.js

Flux :

L’utilisateur clique sur « Corriger ».

La page affiche le barème, les scores (saisie manuelle possible).

Enregistrement audio (Web Speech API pour transcription temps réel, MediaRecorder pour le fichier).

Transcription affichée en temps réel, modifiable.

Clic sur « Sauvegarder et analyser » → appel à /api/correction/save (POST) avec transcript et scores saisis.

Le serveur lance un thread asynchrone synthesize_with_mistral.

Le frontend interroge /api/correction/<id>/status toutes les 2 secondes jusqu’à obtention du résultat.

Affichage de la synthèse, bouton « Publier et générer QR » apparaît.

Publication : appel à /api/correction/<id>/publish → génération QR, statut published.

3.7 API JSON pour corrections
Toutes ces routes sont protégées par @login_required et vérifient l’appartenance à l’enseignant.

Route	Méthode	Body	Retour
/teacher/api/correction/save	POST	{student_id, assignment_id, transcript, scores: [{question_id, score}]}	{ok, correction_id, token}
/teacher/api/correction/<id>/status	GET	–	{status, structured_text, total_score}
/teacher/api/correction/<id>/scores	GET	–	[{question_id, score}]
/teacher/api/correction/<id>/audio	POST	FormData (audio blob)	{ok, audio_url}
/teacher/api/correction/<id>/publish	POST	–	{ok, qr (b64), url}
/teacher/api/correction/<id>/delete	POST	{password}	{ok, assignment_id}
/teacher/api/corrections/delete-bulk	POST	{ids, password}	{ok, deleted}
/teacher/api/correction/<id>/resynthesize	POST	–	{ok}
3.8 Détail d’une correction (correction_detail.html)
Route : GET /teacher/correction/<int:correction_id>

Contenu :

Informations élève et devoir.

Tableau des notes.

Actions :

Publier (si brouillon)

Modifier (redirige vers record.html)

Recalculer la synthèse (si brouillon et transcript présent)

Supprimer (avec mot de passe)

Lecteur audio.

Synthèse Mistral (si présente).

QR code (si publié) avec téléchargement PNG.

Bouton « Aperçu élève » (non encore implémenté – priorité A).

3.9 Appréciation générale de la classe
Intégrée à assignment_corrections.html.

Mini‑recorder (ré‑utilise VoxRecorder) pour dicter une appréciation.

Zone de texte pour saisie manuelle.

Bouton « Reformuler avec Mistral » → appel à /assignments/<id>/appreciation/synthesize.

Bouton « Enregistrer » → sauvegarde texte + upload audio (séparé).

Routes dédiées :

POST /teacher/assignments/<id>/appreciation (texte)

POST /teacher/assignments/<id>/appreciation/audio (upload audio)

POST /teacher/assignments/<id>/appreciation/synthesize (reformulation)

3.10 Impression / export
Impression des corrections : GET /teacher/assignments/<int:assignment_id>/print
Affiche une page prête à l’impression (CSS media print) avec pour chaque élève : nom, alias, note, synthèse, QR code.

Export notes CSV : POST /teacher/admin/export/notes
Paramètres : classes (checkbox), période (date_from, date_to), format (xlsx ou pdf – seul CSV est implémenté).
Génère un CSV téléchargeable.

3.11 Administration (admin.html)
Accès verrouillé : nécessite mot de passe (session admin_unlocked expire après 30 min).

Routes :

GET /teacher/admin – affiche le formulaire de déverrouillage ou le panneau.

POST /teacher/admin/unlock – vérifie mot de passe, pose le flag de session.

GET /teacher/admin/lock – supprime le flag.

POST /teacher/admin/theme – change les couleurs de l’enseignant (theme_primary, theme_secondary, theme_bg).

POST /teacher/admin/delete-account – supprime définitivement le compte (vérification SUPPRIMER + mot de passe).

Le panneau contient aussi :

Import Pronote (modal)

Export notes (modal)

Lien vers « Créer un devoir commun » (placeholder – priorité F)

4. Module public élève (blueprints/public.py)
Préfixe URL : /c

4.1 Visualisation d’une correction – GET /c/<token>
Recherche la Correction avec status='published' et public_token = token.

Log de consultation : IP hashée (HMAC‑SHA256) et user agent sont stockés dans AccessLog.

Récupération des scores pour affichage dans le template.

Template : templates/public/student.html

Fonctionnalités du template :

Jauge circulaire SVG (note en pourcentage, couleur selon seuil).

Tableau des questions cliquable (seek audio).

Pills de navigation par chapitre (basés sur les data-qi des sections).

Lecteur audio avec préchargement à la demande.

Confirmation de lecture à 90% (AJAX vers /c/<token>/read).

Téléchargement de l’audio pour stockage offline (IndexedDB).

Service worker pour cache statique.

4.2 Confirmation de lecture – POST /c/<token>/read
Marque correction.read_at = datetime.now() si encore None.

Idempotent.

Retourne {"ok": True, "read_at": isoformat}.

5. Module pages statiques (blueprints/pages.py)
Préfixe URL : /pages

Routes et templates correspondants :

Route	Template
/pages/documentation	pages/documentation.html
/pages/aide	pages/aide.html
/pages/mentions-legales	pages/mentions_legales.html
/pages/rgpd	pages/rgpd.html
/pages/contact	pages/contact.html
/pages/licence	pages/licence.html
Toutes ces pages sont publiques et accessibles sans authentification.

6. Modèles de données (models/__init__.py)
Relations (diagramme simplifié)
text
Teacher 1──n Classroom 1──n Student 1──n Correction
Classroom 1──n Assignment 1──n Question
Assignment 1──n Correction 1──n QuestionScore
Correction 1──n AccessLog
Détail des colonnes importantes
Modèle	Colonnes clés
Teacher	email (unique), password_hash, first_name, last_name, school, email_verified, verification_token, theme_primary/secondary/bg
Classroom	name, subject, school_year
Student	alias, student_number, encrypted_first_name, encrypted_last_name
Assignment	title, description, date, total_points, class_appreciation, class_appreciation_audio_url
Question	label, max_points, competence, order
Correction	public_token (unique), raw_transcript, structured_text, audio_url, audio_duration, total_score, status (draft/processing/published), read_at
QuestionScore	score (Float)
AccessLog	accessed_at, ip_hash (HMAC‑SHA256), user_agent
Méthodes importantes
Teacher.set_password, check_password, generate_verification_token

Correction.compute_total(), Correction.publish()

7. Services métier (services/)
7.1 ai.py – Mistral
Fonction	Rôle	Particularités
normalize_transcript	Corrige les artefacts Web Speech (3h30 → 3,5).	Utilisée avant l’envoi à Mistral.
synthesize_with_mistral(raw_text, question_labels, question_max)	Appelle mistral-small-latest avec un prompt structuré (JSON).	Retourne {"formatted_text": "...", "grades": [...]}. grades contient question_index, score, max_score.
_fallback	Si API indisponible, parse grossièrement les notes avec regex.	Ne casse pas le thread.
synthesize_appreciation(raw_text)	Reformule une appréciation générale.	Prompt spécifique, retourne {"formatted_text": "..."}.
7.2 anonymization.py
encrypt_name / decrypt_name : Fernet (clé depuis ENCRYPTION_KEY).

generate_alias(first_name, last_name, student_number) : hache les noms, index dans une liste d’animaux → Animal-XX.

Liste des animaux (29 éléments, ex: Renard, Aigle, Bison…).

7.3 background.py
run_in_background(fn, *args, **kwargs) : lance un thread daemon.

Utilisé pour synthesize_with_mistral et resynthesize pour ne pas bloquer la requête HTTP.

7.4 email.py
send_verification_email(to_email, first_name, token) : envoi via l’API REST SendGrid.

Utilise les variables d’environnement SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME.

Construit l’URL de vérification avec APP_BASE_URL.

Retourne True si succès, False sinon (et supprime le compte en cas d’échec dans auth.py).

7.5 qrcode.py
make_qr(token) : retourne {"url": "https://.../c/<token>", "png_b64": "data:image/png;base64,..."} (QR stylisé avec coins arrondis).

qr_png_bytes(token) : retourne les bytes bruts de l’image PNG.

7.6 storage.py – Cloudinary
_configure() : initialise le SDK avec les variables d’environnement.

upload_audio(file_bytes, public_id, teacher_id) : upload le blob, resource_type='video', dossier voxcorr/{teacher_id}. Retourne url, duration, public_id.

delete_audio(public_id) : suppression.

8. Frontend statique (static/)
8.1 CSS – voxcorr.css
Design system complet : variables CSS (--vox-neon, --vox-black, …).

Classes utilitaires : cartes, badges, boutons, formulaires, tableaux, wavefom, jauge, etc.

Media queries pour mobile.

Styles d’impression.

8.2 JavaScript
8.2.1 recorder.js
Classe VoxRecorder (exposée globalement window.VoxRecorder).

Utilise navigator.mediaDevices.getUserMedia pour le flux audio.

Web Speech API (SpeechRecognition ou webkitSpeechRecognition) pour la transcription en temps réel.

MediaRecorder pour capturer le fichier audio (webm).

Méthodes : start(bars), stop(bars).

Callbacks : onTranscript(final, interim), onAudioReady(blob), onStateChange(state).

⚠️ Guard Firefox : non présent actuellement (à ajouter).

8.2.2 record_page.js (module ES6)
Point d’entrée de la page d’enregistrement.

Importe UI (depuis modules/ui.js) et api (depuis modules/api.js).

Initialise un VoxRecorder avec les callbacks qui mettent à jour l’UI.

Gère le polling de Mistral, l’upload audio, la publication.

8.2.3 modules/api.js et modules/ui.js
api.js : centralise tous les appels fetch (CSRF automatiquement ajouté). Exports : saveCorrection, getStatus, uploadAudio, publish.

ui.js : machine à états (idle, recording, stopped, processing, done, published). Gère l’affichage/masquage des boutons, la mise à jour des zones de texte et la récupération des scores saisis.

8.2.4 sw.js – Service worker
Cache les assets statiques (CSS, recorder.js, Bootstrap CSS).

Ne cache jamais les fichiers audio (domaine Cloudinary).

Intercepte les requêtes /c/* (page élève) pour les servir depuis le cache en cas d’absence de réseau.

8.3 manifest.json
Nom, short_name, start_url (/), theme_color (#39FF14), background_color (#0a0a0a), display (standalone).

9. Templates (templates/)
9.1 base.html
Layout commun : navbar, footer, inclusion de Bootstrap Icons, CSS, JS.

Injecte csrf_token() dans une balise <meta name="csrf-token">.

Affiche les messages flash (toasts Bootstrap).

Définit les blocs title, head, content, scripts.

9.2 components/modals.html
Trois modales génériques :

vox-modal-confirm (confirmation d’action)

vox-modal-alert (alerte d’information)

vox-modal-loading (chargement)

API JavaScript VoxModal.confirm(), VoxModal.alert(), VoxModal.loading() / stopLoading().

9.3 Templates d’erreur
errors/403.html, 404.html, 429.html, 500.html

Héritent de base.html, affichent un message et des liens de retour.

9.4 Templates d’authentification
auth/login.html, auth/register.html (avec barre de force du mot de passe, affichage/masquage).

9.5 Templates des pages statiques
pages/documentation.html : guide utilisateur complet, sidebar déroulante, sections avec ancres.

pages/aide.html : accordéon de problèmes courants.

pages/contact.html : carte de contact, délais.

pages/mentions_legales.html, pages/rgpd.html, pages/licence.html (texte juridique).

9.6 Templates enseignant
Template	Rôle
teacher/dashboard.html	Tableau de bord (groupement par discipline)
teacher/classes.html	Liste des classes (cartes)
teacher/class_detail.html	Détail classe (élèves + devoirs)
teacher/new_class.html	Formulaire création classe
teacher/assignment_corrections.html	Vue devoir (liste élèves + barème + appréciation + suppression groupée + stats)
teacher/correction_detail.html	Détail d’une correction (audio, notes, QR, actions)
teacher/record.html	Page d’enregistrement (micro, transcript, scores)
teacher/print_corrections.html	Page d’impression des corrections (CSS print)
teacher/admin.html	Panneau d’administration (déverrouillage, thème, import, export, suppression compte)
teacher/new_assignment.html	Création devoir avec questions dynamiques
teacher/edit_assignment.html	Édition devoir (champs simples)
teacher/edit_student.html	Modification d’un élève
9.7 Template élève – public/student.html
JavaScript intégré (pas de module) : gestion de la jauge SVG, des chapitres, du seek audio, de la confirmation de lecture, du stockage offline (IndexedDB).

Surcharge possible via window.VC_PREVIEW_MODE pour désactiver la confirmation (utilisé pour l’aperçu enseignant).

10. Fonctionnalités manquantes (priorisées)
Rappel de la section 6 du prompt initial, avec fichiers cibles.

Priorité	Fonctionnalité	Fichiers concernés
🔴 A	Prévisualisation “vue élève”	teacher.py (ajout route), correction_detail.html (bouton), student.html (flag preview)
🟡 B	Phrases types réutilisables	models/__init__.py (nouveau modèle Phrase), teacher.py (CRUD), record.html (interface), services/
🟡 C	Export PDF correction individuelle	teacher.py (route), services/pdf.py (à créer), correction_detail.html (bouton)
🟡 D	Progression élève multi-devoirs	teacher.py, models/__init__.py (champ Student.compétences ou table dédiée), class_detail.html
🟡 E	Rappel automatique d’écoute	teacher.py (tâche cron ou background), services/email.py, models (flag reminder_sent)
🟢 F	Devoir commun multi-classes	teacher.py (remplacer placeholder), new_assignment.html (sélecteur classes)
🟢 G	Mode saisie rapide	record_page.js, record.html (passage auto au suivant)
🟢 H	Notification email élève à la publication	teacher.py (dans publish_correction), services/email.py (fonction send_student_notification)
🟢 I	Tableau de bord élève par alias	public.py (nouvelle route), student_dashboard.html, QR code de classe
🟢 J	Partage natif mobile (Web Share API)	student.html (bouton avec navigator.share)
🟢 K	Feedback élève après écoute	student.html (formulaire), teacher.py (route de collecte), models (table Feedback)
11. Annexe – Liste complète des routes
Authentification (/auth)
Route	Méthode	Description
/login	GET, POST	Connexion
/register	GET, POST	Inscription
/verify/<token>	GET	Confirmation email
/logout	GET	Déconnexion
Enseignant (/teacher)
Route	Méthode	Description
/dashboard	GET	Tableau de bord
/classes	GET	Liste des classes
/classes/new	GET, POST	Création classe
/classes/<id>	GET	Détail classe
/classes/<id>/delete	POST	Suppression classe
/classes/<id>/students/add	POST	Ajout élève
/classes/<id>/students/<sid>/edit	GET, POST	Modifier élève
/classes/<id>/students/<sid>/delete	POST	Supprimer élève
/classes/<id>/import/csv	POST	Import CSV dans une classe
/import/pronote-file	POST	Import global Pronote
/assignments/new/<class_id>	GET, POST	Nouveau devoir
/assignments/<id>/edit	GET, POST	Modifier devoir
/assignments/<id>/delete	POST	Supprimer devoir
/assignments/<id>/corrections	GET	Liste corrections du devoir
/assignments/<id>/print	GET	Page d’impression
/assignments/<id>/appreciation	POST	Sauvegarde appréciation texte
/assignments/<id>/appreciation/audio	POST	Upload audio appréciation
/assignments/<id>/appreciation/synthesize	POST	Reformulation Mistral
/record/<student_id>/<assignment_id>	GET	Page enregistrement
/correction/<id>	GET	Détail correction
/correction/<id>/qr.png	GET	Téléchargement QR code
/api/correction/save	POST	Sauvegarde correction (brut)
/api/correction/<id>/status	GET	Statut Mistral
/api/correction/<id>/scores	GET	Récupération scores IA
/api/correction/<id>/audio	POST	Upload audio
/api/correction/<id>/publish	POST	Publication
/api/correction/<id>/delete	POST	Suppression unitaire
/api/corrections/delete-bulk	POST	Suppression groupée
/api/correction/<id>/resynthesize	POST	Recalcul Mistral
/admin	GET	Panneau admin (verrouillé)
/admin/unlock	POST	Déverrouillage admin
/admin/lock	GET	Verrouillage admin
/admin/theme	POST	Changement thème
/admin/delete-account	POST	Suppression compte
/admin/export/notes	POST	Export CSV notes
Public élève (/c)
Route	Méthode	Description
/c/<token>	GET	Page élève
/c/<token>/read	POST	Confirmation d’écoute
Pages statiques (/pages)
Route	Méthode
/pages/documentation	GET
/pages/aide	GET
/pages/mentions-legales	GET
/pages/rgpd	GET
/pages/contact	GET
/pages/licence	GET
Autres
Route	Méthode	Description
/	GET	Redirige vers /auth/login
/ping	GET	Health check (Render)