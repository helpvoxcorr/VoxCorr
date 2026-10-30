# Audit complet VoxCorr — Juin 2026

> Photo fidèle de l'application au moment de l'audit. Sert de référence avant la refonte design et les corrections de bugs.

---

## 1. Vue d'ensemble de l'architecture

### Stack
- **Backend** : Flask, SQLAlchemy, Flask-Login, Flask-Migrate (Alembic), Flask-WTF (CSRF), Flask-Limiter, Flask-SocketIO
- **Base de données** : PostgreSQL (Neon, serverless) en prod, SQLite en local
- **Stockage audio** : Cloudinary (`resource_type='video'`, conversion systématique en `.mp3`)
- **IA** : Mistral AI (`mistral-small-latest` pour synthèse/notation, `voxtral-mini-latest` pour transcription)
- **TTS** : Edge TTS (gratuit, sans clé, voix `fr-FR-DeniseNeural`)
- **Email** : SendGrid (appel HTTP direct via `urllib`, pas de SDK)
- **Hébergement** : Render.com (tier gratuit, pas d'accès aux logs — d'où les routes de debug)
- **Front** : Bootstrap 5.3.3, Bootstrap Icons, police Inter (DM Sans/DM Mono mentionnés mais Inter chargée dans `base.html`)

### Authentification — deux systèmes parallèles
| Espace | Mécanisme | Modèle |
|---|---|---|
| Enseignant | Flask-Login (session) | `Teacher` |
| Élève connecté | Session manuelle (`session['pupil_id']`) | `Pupil` (code d'accès 8 caractères) |
| Élève via QR/lien public | Token public, sans auth | `Correction.public_token` |

Trois niveaux d'accès élève coexistent : dashboard connecté (`student.*`), page publique par token (`public.student_view`), et PDF imprimé avec QR (`teacher_corr.correction_pdf`). Ces trois surfaces affichent des informations qui se recoupent largement mais avec des templates et des designs totalement différents (voir section 4).

### Modèle relationnel (synthèse)
```
Teacher 1──N Classroom 1──N Student 1──1 Pupil
                  │              │
                  │              └──N Correction N──1 Assignment
                  │                       │
                  N Assignment 1──N Question 1──N QuestionScore
                  │
                  N Group N──N Student (via GroupStudent)
                  
Correction 1──N AccessLog
Competence (socle commun OU teacher_id spécifique) ──N Question
ClassroomTeacher : table d'association pour la collaboration multi-profs
```

### Inventaire des Blueprints
| Blueprint | Préfixe | Rôle |
|---|---|---|
| `auth` | `/auth` | Login/register/verify email enseignant |
| `public` | *(racine)* | Page élève publique par token (`/c/<token>`) |
| `pages` | `/pages` | Pages statiques (doc, aide, légal, contact) |
| `student` | `/student` | Espace élève connecté (code d'accès) |
| `teacher_crud` | `/teacher` | CRUD classes/élèves/devoirs/groupes/imports |
| `teacher_corr` | `/teacher` | Corrections, enregistrement, appréciation classe, compétences |
| `teacher_admin` | `/teacher` | Zone admin verrouillée (thème, export, suppression compte) |
| `teacher_stats` | `/teacher` | Stats JSON (graphiques, prédictions de risque) |

---

## 2. Bugs identifiés

### 🔴 Bloquant — lien mort confirmé
**`teacher_crud.import_pronote_file`** redirige vers `url_for('teacher_crud.admin')` — **cette route n'existe pas** dans `teacher_crud_bp`. La route admin réelle est `teacher_admin.admin`. Pourtant le formulaire d'import Pronote (modale dans `admin.html`, servie par `teacher_admin.admin`) pointe bien vers cette fonction.

**Effet** : l'import réussit (les élèves sont bien créés en base), mais la page plante avec une `BuildError` au moment de la redirection finale. L'utilisateur ne voit jamais le message de succès et atterrit sur une page 500.

**Fichier** : `app/blueprints/teacher_crud.py`, fonction `import_pronote_file`, dernière ligne.

### 🔴 Bloquant — pages légales tronquées
`licence.html` et `mentions_legales.html` sont incomplets sur le disque (confirmé par deux envois identiques). 
- `licence.html` coupe en plein article 5 « Données personnelles », pas de fermeture HTML/Jinja.
- `mentions_legales.html` coupe en pleine ouverture d'une `<div class="card">`, juste après la section "Limitation de responsabilité".

**Effet** : rendu HTML cassé en production sur deux pages à valeur légale. À corriger dès que le texte complet est fourni.

### 🟠 Probable bug — `edit_group.html` / noms non déchiffrés
La route `teacher_crud.edit_group` charge les élèves sans appeler `decrypt_name` :
```python
students = Student.query.filter_by(classroom_id=class_id).all()
```
Le template affiche pourtant `s.display_last` / `s.display_first`, des attributs qui n'existent que lorsque la route les calcule explicitement (pattern vu dans `class_detail`, `assignment_corrections`, etc.). Ici, ils ne sont jamais posés sur les objets.

**Effet probable** : la liste des membres du groupe affiche des champs vides ou lève une erreur de rendu Jinja silencieuse (`Undefined`), selon la configuration Jinja.

### 🟡 À vérifier — pages élève sans style rattaché
`student/dashboard.html` et `student/correction.html` utilisent des classes CSS (`dashboard-container`, `stat-card`, `corr-hero-premium`, `glass-card`, `q-score-pill`, etc.) absentes de `voxcorr.css`. Confirmé par recherche exhaustive dans le fichier. Ces deux pages sont donc probablement non stylées en l'état, ou stylées par un fichier non communiqué. **Décision prise** : ces pages seront réintégrées dans le nouveau design system à concevoir, donc ce point n'est plus un bug à corriger isolément mais une entrée du chantier de refonte.

### 🟡 Mineur — JWT mort ou orphelin
`app/utils/security.py` contient un système JWT complet (`generate_token`, `token_required`, décorateur prêt à l'emploi) qui n'apparaît utilisé dans aucun blueprint lu. Soit du code mort à supprimer, soit préparé pour un usage futur (API mobile ?) non encore branché. À clarifier avec toi avant suppression.

### 🟡 Mineur — doublon de hachage de mot de passe
`security.py` définit `hash_password`/`verify_password` (wrappers `werkzeug.security`), qui font doublon avec `Teacher.set_password`/`check_password` déjà sur le modèle et utilisés partout ailleurs. Les fonctions de `security.py` semblent non utilisées.

---

## 3. Duplications de code repérées

### Pattern d'autorisation incohérent
Le contrôle "cette ressource appartient-elle au prof connecté ?" s'écrit de trois façons différentes selon le fichier/la fonction :
```python
# Forme 1 (la plus sûre, une ligne)
Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()

# Forme 2
c = db.session.get(Classroom, class_id)
if not c or c.teacher_id != current_user.id: abort(404)

# Forme 3 (avec flash + redirect au lieu d'abort)
a = db.session.get(Assignment, assignment_id)
if not a: abort(404)
if a.classroom.teacher_id != current_user.id:
    flash('Accès non autorisé.', 'danger')
    return redirect(url_for('teacher_crud.dashboard'))
```
Présent dans `teacher_crud.py`, `teacher_corrections.py`, `teacher_admin.py`. Bon candidat pour un décorateur (`@require_classroom_owner` ou équivalent) ou une fonction utilitaire centralisée.

### Déduplication CSV élèves
`import_csv_class` et `import_pronote_file` (`teacher_crud.py`) répètent presque à l'identique : construction d'un `set` de tuples `(nom, prénom)` en minuscules pour détecter les doublons, puis boucle d'ajout incrémentant `student_number`. Extractible en fonction commune `import_students(classroom, rows, name_extractor)`.

### Modale de suppression avec URL construite en JS
`classes.html` (`confirmDelete`) et `dashboard.html` (`showDeleteModal`) ont chacun une fonction JS quasi identique qui construit l'URL de suppression en concaténant une chaîne (`"/teacher/classes/" + id + "/delete"`) plutôt que via `url_for` côté Jinja. Fragile si la route change.

**Point notable** : un composant générique existe déjà et est sous-utilisé — `components/modals.html` (`VoxModal.confirm/alert/loading`) est exactement l'outil qui devrait remplacer ces deux implémentations ad hoc. À vérifier : est-il seulement inclus dans certaines pages, ou pas inclus dans `base.html` du tout ?

### FAQ dupliquée
`pages/aide.html` et `pages/documentation.html` ont chacune leur propre accordéon FAQ, avec des questions qui se recoupent fortement (micro, Mistral, QR code, audio Cloudinary). Pas un bug, mais une redondance de contenu à clarifier (fusion ou rôles distincts à affirmer).

---

## 4. Collision de conventions de nommage CSS

Le préfixe **`cd-`** est utilisé pour deux familles de classes complètement différentes :

| Famille A — Class Detail | Famille B — Correction Detail + Record |
|---|---|
| `cd-hero`, `cd-pill`, `cd-student-row` | `cd-hero`, `cd-pill` *(réutilisés à l'identique, cohérent ici)* |
| `cd-assignment-row`, `cd-add-form` | `cd-header`, `cd-status`, `cd-score-card` |
| *(`class_detail.html` uniquement)* | `cd-q-advice`, `cd-qr-section`, `cd-btn-primary` |
| | *(partagé entre `correction_detail.html` et `record.html`)* |

`record.html` et `correction_detail.html` partagent correctement le même sous-système `cd-*`. Le vrai conflit est entre **`class_detail.html`** (sens A) et **tout le reste** (sens B), qui réutilisent les mêmes noms de classes racines (`cd-hero`, `cd-pill`, `cd-card`) pour des mises en page différentes. Ça fonctionne aujourd'hui par coïncidence (les noms complets ne se recoupent jamais exactement), mais c'est fragile.

### Trois systèmes de design coexistants, sans recouvrement
1. **`vox-*`** — système principal (`voxcorr.css`), utilisé par : navbar, footer, cards génériques, formulaires, login/register, dashboard, classes, admin, modales.
2. **`ac-*`** (assignment-corrections), **`cd-*`** (class/correction detail), **`dash-*`** (dashboard), **`rec-*`** (record) — préfixes page-spécifiques, chacun avec ses propres cards/boutons/badges qui réinventent des motifs déjà présents dans `vox-*` (ex. `.ac-card` vs `.cd-card` vs `.vox-card` sont trois implémentations de la même idée de carte).
3. **Systèmes non rattachés à `voxcorr.css`** — `dashboard-container`/`stat-card` (student dashboard) et `corr-hero-premium`/`glass-card` (student correction), dont le CSS source est introuvable dans les fichiers fournis.

**Conclusion pour la refonte** : il n'y a pas un design system avec des variantes, il y a 3+ vocabulaires CSS indépendants qui résolvent les mêmes problèmes (cartes, boutons, badges de statut, hero de page) de façons différentes. La refonte from-scratch validée avec toi est la bonne décision — un raccord progressif aurait nécessité de désambiguïser ces collisions une par une avant même de commencer le nouveau design.

---

## 5. Inventaire des écrans par contexte (pour le futur design system)

### Espace enseignant connecté
Dashboard · Liste classes · Détail classe · Nouvelle/Édition classe · Édition élève · Édition groupe · Nouveau/Édition devoir · Liste corrections d'un devoir · Détail correction · Enregistrement correction (recorder) · Impression corrections · Compétences · Administration (thème, export, import, suppression compte)

### Espace élève connecté (code d'accès)
Login par code · Dashboard (liste corrections) · Détail correction

### Page publique (sans auth, via token)
Page correction élève (`/c/<token>`) — affiche aussi l'appréciation de classe (texte, audio à ajouter)

### Pages légales/publiques
Login/Register enseignant · Documentation · Aide · Mentions légales · RGPD · Contact · Licence · Erreurs (403/404/429/500)

### PDF (hors design system web)
`correction_pdf.html` — gabarit autonome WeasyPrint, CSS inline, non concerné par la refonte `voxcorr.css`

---

## 6. Ce qui fonctionne bien — à préserver

- **Pages d'erreur** (403/404/429/500) : structure DRY exemplaire, gestion correcte auth/anonyme.
- **`components/modals.html`** : API JS propre et réutilisable (`VoxModal`), juste sous-exploitée.
- **Anonymisation RGPD** (`anonymization.py`) : alias déterministe élégant, chiffrement Fernet correctement isolé.
- **`background.py`** : choix pragmatique (thread daemon plutôt que Celery) documenté et justifié pour le tier Render gratuit.
- **Services IA** (`ai.py`) : prompts très détaillés et précis, gestion d'erreur cohérente avec fallback, jamais de plantage du thread appelant.
- **Système de breadcrumb dynamique** : élégant, piloté par une config déclarative.

---

## 7. Plan d'action proposé

### Phase 1 — Corrections ponctuelles (avant refonte design)
1. Corriger le lien mort `teacher_crud.admin` → `teacher_admin.admin`
2. Compléter les deux pages légales tronquées (texte à fournir)
3. Corriger `edit_group` (ajouter le déchiffrement des noms)
4. Clarifier le sort du système JWT (`security.py`) — garder ou supprimer
5. Vérifier l'inclusion de `components/modals.html` dans `base.html`

### Phase 2 — Conception du nouveau design system (from scratch)
- Définir tokens (couleurs, typographie, espacements, rayons) — une seule source de vérité
- Définir les composants de base (cards, boutons, badges, inputs, status pills) réutilisables sur tous les contextes
- Couvrir explicitement les 4 contextes : prof connecté / élève connecté / page publique élève / légal-public
- Décider du sort de l'identité visuelle actuelle (noir/blanc/vert neon) vs nouvelle direction

### Phase 3 — Migration page par page
- Ordre suggéré : pages à fort trafic élève d'abord (page publique, dashboard élève) ou pages prof d'abord (à décider ensemble)
- Suppression progressive de l'ancien `voxcorr.css` au fur et à mesure

### Phase 4 — Factorisation du code Python (en parallèle ou après)
- Décorateur/fonction d'autorisation centralisée
- Fonction commune d'import CSV élèves
- Suppression du code mort identifié

---

*Document généré à partir de l'audit du 23 juin 2026 — 9 modèles, 8 blueprints, 7 services/utils, 29 templates, 1 fichier CSS (1242 lignes).*