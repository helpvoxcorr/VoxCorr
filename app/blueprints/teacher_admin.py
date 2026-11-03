from flask import (Blueprint, render_template, redirect, url_for, request, jsonify, flash, send_file, current_app, session, abort)
from flask_login import login_required, current_user, logout_user
from app.extensions import db, limiter
from app.models import Classroom, Student, Pupil, Teacher, Competence
from app.services.anonymization import decrypt_name
from app.services.qrcode import public_base_url
import io, csv, re, os, secrets
from datetime import datetime, timezone, timedelta

teacher_admin_bp = Blueprint('teacher_admin', __name__, url_prefix='/teacher')

def is_admin_session_valid():
    unlocked_at = session.get('admin_unlocked_at')
    if not unlocked_at: return False
    try: unlocked_dt = datetime.fromisoformat(unlocked_at); return datetime.now(timezone.utc) - unlocked_dt < timedelta(minutes=30)
    except Exception: return False

def is_site_admin():
    """Administrateur du site : l'adresse e-mail est dans la variable ADMIN_EMAIL."""
    admin = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    return bool(admin) and current_user.is_authenticated and (current_user.email or '').lower() == admin

def sanitize_csv_field(value):
    if not value: return value
    value = str(value)
    if value.startswith(('=', '+', '-', '@')): return "\t" + value
    return value

@teacher_admin_bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if current_user.check_password(password): session['admin_unlocked'] = True; session['admin_unlocked_at'] = datetime.now(timezone.utc).isoformat()
        else: session['admin_lock_error'] = 'Mot de passe incorrect.'
        return redirect(url_for('teacher_admin.admin'))
    lock_error = session.pop('admin_lock_error', None); classrooms = []
    if session.get('admin_unlocked') and is_admin_session_valid(): classrooms = Classroom.query.filter_by(teacher_id=current_user.id).order_by(Classroom.name).all()
    return render_template('teacher/admin.html', classrooms=classrooms, lock_error=lock_error,
                           is_site_admin=is_site_admin())

@teacher_admin_bp.route('/admin/lock')
@login_required
def admin_lock():
    session.pop('admin_unlocked', None); session.pop('admin_unlocked_at', None); return redirect(url_for('teacher_crud.dashboard'))

@teacher_admin_bp.route('/admin/theme', methods=['POST'])
@login_required
def admin_theme():
    if not session.get('admin_unlocked') or not is_admin_session_valid(): return redirect(url_for('teacher_admin.admin'))
    themes = {'neon': {'primary': '#39FF14', 'secondary': '#0a0a0a', 'bg': '#ffffff'}, 'ardoise': {'primary': '#6366f1', 'secondary': '#1e293b', 'bg': '#f8fafc'}, 'soleil': {'primary': '#f59e0b', 'secondary': '#92400e', 'bg': '#fffbeb'}, 'ocean': {'primary': '#0ea5e9', 'secondary': '#0c4a6e', 'bg': '#f0f9ff'}}
    t = themes.get(request.form.get('theme', 'neon'))
    if t: current_user.theme_primary = t['primary']; current_user.theme_secondary = t['secondary']; current_user.theme_bg = t['bg']; db.session.commit(); flash('Thème appliqué.', 'success')
    return redirect(url_for('teacher_admin.admin'))

@teacher_admin_bp.route('/admin/delete-account', methods=['POST'])
@login_required
def admin_delete_account():
    if not session.get('admin_unlocked') or not is_admin_session_valid(): return redirect(url_for('teacher_admin.admin'))
    confirm = request.form.get('confirm', ''); password = request.form.get('password', '')
    if confirm != 'SUPPRIMER' or not current_user.check_password(password): flash('Confirmation incorrecte.', 'danger'); return redirect(url_for('teacher_admin.admin'))
    user = current_user._get_current_object(); logout_user(); db.session.delete(user); db.session.commit(); flash('Compte supprimé.', 'success'); return redirect(url_for('auth.login'))

@teacher_admin_bp.route('/admin/generate-access-codes', methods=['POST'])
@login_required
def generate_access_codes():
    if not session.get('admin_unlocked') or not is_admin_session_valid():
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('teacher_admin.admin'))
    class_id = request.form.get('class_id', type=int)
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    created = 0
    for student in classroom.students:
        if not Pupil.query.filter_by(student_id=student.id).first():
            db.session.add(Pupil(student_id=student.id, access_code=Pupil.generate_access_code()))
            created += 1
    db.session.commit()
    flash(f'{created} code(s) généré(s).' if created else 'Tous les élèves ont déjà un code.', 'success')
    return redirect(url_for('teacher_admin.access_codes', class_id=class_id))


@teacher_admin_bp.route('/admin/access-codes')
@login_required
def access_codes():
    if not session.get('admin_unlocked') or not is_admin_session_valid():
        flash('Saisissez votre mot de passe pour accéder aux codes.', 'warning')
        return redirect(url_for('teacher_admin.admin'))
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id).order_by(Classroom.name).all()
    class_id = request.args.get('class_id', type=int)
    selected = next((c for c in classrooms if c.id == class_id), classrooms[0] if classrooms else None)
    rows = []
    if selected:
        for s in Student.query.filter_by(classroom_id=selected.id).order_by(Student.student_number).all():
            try:
                last = decrypt_name(s.encrypted_last_name)
                first = decrypt_name(s.encrypted_first_name)
            except Exception:
                last = first = '—'
            pupil = Pupil.query.filter_by(student_id=s.id).first()
            rows.append({'last': last, 'first': first, 'alias': s.alias,
                         'code': pupil.access_code if pupil else None})
        rows.sort(key=lambda r: (r['last'].lower(), r['first'].lower()))
    missing = sum(1 for r in rows if not r['code'])
    return render_template('teacher/access_codes.html', classrooms=classrooms, selected=selected,
                           rows=rows, missing=missing, login_url=f'{public_base_url()}/student/login')

@teacher_admin_bp.route('/admin/export/notes', methods=['POST'])
@login_required
def admin_export_notes():
    if not session.get('admin_unlocked') or not is_admin_session_valid(): return redirect(url_for('teacher_admin.admin'))
    class_ids = request.form.getlist('class_ids', type=int); date_from_str = request.form.get('date_from'); date_to_str = request.form.get('date_to')
    try: date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date() if date_from_str else None; date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date() if date_to_str else None
    except ValueError: date_from = date_to = None
    query = Classroom.query.filter_by(teacher_id=current_user.id)
    if class_ids: query = query.filter(Classroom.id.in_(class_ids))
    classrooms = query.all()
    if not classrooms: flash('Aucune classe sélectionnée.', 'warning'); return redirect(url_for('teacher_admin.admin'))
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(['Classe', 'Élève', 'Devoir', 'Date', 'Note', 'Sur', 'Statut'])
    for classroom in classrooms:
        for assignment in classroom.assignments:
            if date_from and assignment.date and assignment.date < date_from: continue
            if date_to and assignment.date and assignment.date > date_to: continue
            for correction in assignment.corrections:
                try: first = decrypt_name(correction.student.encrypted_first_name); last = decrypt_name(correction.student.encrypted_last_name); name = f"{last} {first}"
                except Exception: name = correction.student.alias
                writer.writerow([sanitize_csv_field(classroom.name), sanitize_csv_field(name), sanitize_csv_field(assignment.title), sanitize_csv_field(assignment.date.strftime('%d/%m/%Y') if assignment.date else ''), sanitize_csv_field(correction.total_score if correction.total_score is not None else ''), sanitize_csv_field(assignment.total_points), sanitize_csv_field(correction.status)])
    output.seek(0); filename = f"notes_export_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=filename)

@teacher_admin_bp.route('/admin/import-competences', methods=['POST'])
@login_required
def import_competences():
    if not session.get('admin_unlocked') or not is_admin_session_valid(): flash('Accès non autorisé.', 'danger'); return redirect(url_for('teacher_admin.admin'))
    if 'csv_file' not in request.files: flash('Aucun fichier sélectionné.', 'danger'); return redirect(url_for('teacher_admin.admin'))
    file = request.files['csv_file']
    if file.filename == '' or not file.filename.lower().endswith('.csv'): flash('Fichier CSV invalide.', 'danger'); return redirect(url_for('teacher_admin.admin'))
    subject = request.form.get('subject', '').strip()
    if not subject: flash('La matière est obligatoire.', 'danger'); return redirect(url_for('teacher_admin.admin'))
    try:
        raw_data = file.read()
        for encoding in ['utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']:
            try: content = raw_data.decode(encoding); break
            except UnicodeDecodeError: continue
        else: raise Exception("Encodage non supporté")
        reader = csv.DictReader(content.splitlines(), delimiter='\t'); created = updated = 0
        for row in reader:
            col1 = list(row.keys())[0].strip('"').strip(); name = row[col1].strip().strip('"').split(';')[0].strip(); domain_raw = row.get('Domaines du socle pour les bilans de cycle', '').strip().strip('"')
            if not name: continue
            domain = None
            if domain_raw:
                match = re.search(r'D[1-5]', domain_raw)
                if match: domain = match.group(0)
            existing = Competence.query.filter_by(name=name, subject=subject, teacher_id=current_user.id).first()
            if existing:
                if existing.domain != domain: existing.domain = domain; updated += 1
            else:
                socle = Competence.query.filter_by(name=name, subject=subject, teacher_id=None).first()
                if socle: socle.teacher_id = current_user.id; socle.domain = domain; updated += 1
                else: db.session.add(Competence(name=name, domain=domain, subject=subject, teacher_id=current_user.id)); created += 1
        db.session.commit(); flash(f'Import terminé : {created} créée(s), {updated} mise(s) à jour.', 'success')
    except Exception as e: db.session.rollback(); current_app.logger.error(f"Import CSV competences error: {e}"); flash("Erreur lors de l'import.", 'danger')
    return redirect(url_for('teacher_admin.admin'))

@teacher_admin_bp.route('/admin/reset-year', methods=['POST'])
@login_required
def reset_year():
    if not session.get('admin_unlocked') or not is_admin_session_valid():
        return redirect(url_for('teacher_admin.admin'))
    
    confirm = request.form.get('confirm', '')
    password = request.form.get('password', '')
    
    if confirm != 'RESET' or not current_user.check_password(password):
        flash('Confirmation incorrecte.', 'danger')
        return redirect(url_for('teacher_admin.admin'))
    
    from app.models import Classroom
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id).all()
    for classroom in classrooms:
        db.session.delete(classroom)
    db.session.commit()
    
    flash('Remise à zéro effectuée. Toutes vos classes ont été supprimées.', 'success')
    return redirect(url_for('teacher_crud.dashboard'))

@teacher_admin_bp.route('/admin/accounts', methods=['GET', 'POST'])
@login_required
def accounts():
    if not is_site_admin():
        abort(404)   # la page n'existe pas pour les autres
    if not session.get('admin_unlocked') or not is_admin_session_valid():
        flash('Saisissez votre mot de passe pour accéder à cette page.', 'warning')
        return redirect(url_for('teacher_admin.admin'))

    from app.blueprints.auth import make_reset_token, EMAIL_PATTERN
    link = target = None

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            email = request.form.get('email', '').strip().lower()
            if not re.match(EMAIL_PATTERN, email):
                flash('Adresse e-mail invalide.', 'warning')
            elif Teacher.query.filter_by(email=email).first():
                flash('Un compte existe déjà avec cette adresse.', 'warning')
            else:
                t = Teacher(email=email,
                            first_name=request.form.get('first_name', '').strip(),
                            last_name=request.form.get('last_name', '').strip(),
                            school=request.form.get('school', '').strip())
                t.set_password(secrets.token_urlsafe(32))   # inutilisable : la personne choisira le sien
                t.email_verified = True
                db.session.add(t)
                db.session.commit()
                target = t
                link = url_for('auth.reset_password', token=make_reset_token(t), _external=True)
                current_app.logger.info('Compte créé par l\'administrateur : %s', email)
                flash('Compte créé. Transmettez le lien ci-dessous à la personne.', 'success')
        else:
            target = db.session.get(Teacher, request.form.get('teacher_id', type=int) or 0)
            if not target:
                flash('Compte introuvable.', 'danger')
            elif action == 'reset':
                link = url_for('auth.reset_password', token=make_reset_token(target), _external=True)
                current_app.logger.info('Lien généré pour %s', target.email)
            elif action == 'suspend':
                if target.id == current_user.id:
                    flash('Vous ne pouvez pas suspendre votre propre compte.', 'warning')
                else:
                    target.email_verified = False
                    target.set_password(secrets.token_urlsafe(32))   # invalide aussi les anciens liens
                    db.session.commit()
                    current_app.logger.info('Compte suspendu : %s', target.email)
                    flash(f'Compte de {target.first_name} {target.last_name} suspendu. Ses données sont conservées.', 'success')
                target = None

    teachers = Teacher.query.order_by(Teacher.last_name, Teacher.first_name).all()
    rows = [{'t': t, 'classes': Classroom.query.filter_by(teacher_id=t.id).count()} for t in teachers]
    return render_template('teacher/accounts.html', rows=rows, link=link, target=target)