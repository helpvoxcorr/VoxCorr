from flask import Blueprint, render_template, request, jsonify
from app import db
from app.models import Correction, AccessLog
from app.utils.security import hash_ip
from datetime import datetime, timezone

public_bp = Blueprint('public', __name__)

@public_bp.route('/c/<token>')
def student_view(token):
    """
    Page publique de correction élève.
    Accessible via QR code — aucun compte requis.
    Chaque visite est loggée (IP hashée, jamais en clair).
    """
    corr = Correction.query.filter_by(
        public_token=token, status='published'
    ).first_or_404()

    # Log de consultation RGPD : IP hashée SHA-256
    ip      = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    ip      = ip.split(',')[0].strip()   # X-Forwarded-For peut valoir "ip1, ip2, ..."
    ip_hash = hash_ip(ip)
    db.session.add(AccessLog(
        correction_id = corr.id,
        ip_hash       = ip_hash,
        user_agent    = (request.user_agent.string or '')[:255],
    ))
    db.session.commit()

    scores_detail = [
        {
            'label':      qs.question.label,
            'score':      qs.score,
            'max':        qs.question.max_points,
            'competence': qs.question.competence,
        }
        for qs in corr.scores
    ]

    return render_template('public/student.html',
                           correction    = corr,
                           scores        = scores_detail,
                           teacher       = corr.assignment.classroom.teacher)
 
 
@public_bp.route('/c/<token>/read', methods=['POST'])
def mark_as_read(token):
    """
    Marque la correction comme lue (appelé automatiquement après 90% d'écoute).
    Idempotent : ne met à jour read_at que si pas encore défini.
    """
    corr = Correction.query.filter_by(
        public_token=token, status='published'
    ).first_or_404()
 
    if corr.read_at is None:
        corr.read_at = datetime.now(timezone.utc)
        db.session.commit()
 
    return jsonify({'ok': True, 'read_at': corr.read_at.isoformat()})