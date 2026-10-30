from flask import Blueprint, jsonify, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Classroom, Student, Correction, Assignment

teacher_stats_bp = Blueprint('teacher_stats', __name__, url_prefix='/teacher')

@teacher_stats_bp.route('/api/stats/class/<int:class_id>')
@login_required
def class_stats(class_id):
    classroom = Classroom.query.filter_by(id=class_id, teacher_id=current_user.id).first_or_404()
    data = {'labels': [], 'scores': [], 'competences': {}}
    for assignment in classroom.assignments:
        data['labels'].append(assignment.title)
        avg_score = sum(c.total_score or 0 for c in assignment.corrections) / max(len(assignment.corrections), 1)
        data['scores'].append(avg_score)
    return jsonify(data)

@teacher_stats_bp.route('/api/stats/level/<level>')
@login_required
def level_stats(level):
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id, level=level).all(); result = []
    for c in classrooms:
        scores = []
        for a in sorted(c.assignments, key=lambda x: x.date or x.created_at):
            corrs = [corr.total_score for corr in a.corrections if corr.total_score is not None]
            if corrs: scores.append(sum(corrs) / len(corrs))
        avg = round(sum(scores) / len(scores), 2) if scores else None; trend = None
        if len(scores) >= 2: trend = 'up' if scores[-1] > scores[-2] else 'down'
        result.append({'name': c.name, 'avg': avg, 'trend': trend, 'nb_devoirs': len(c.assignments)})
    return jsonify({'classes': result, 'level': level})

@teacher_stats_bp.route('/api/student/<int:student_id>/competence-stats')
@login_required
def student_competence_stats(student_id):
    student = Student.query.get_or_404(student_id)
    if student.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    corrections = Correction.query.filter_by(student_id=student_id, status='published').order_by(Correction.created_at).all()
    if not corrections: return jsonify({'competences': [], 'evolution': []})
    comp_scores = {}; evolution = []
    for corr in corrections:
        evolution.append({'devoir': corr.assignment.title, 'note': corr.total_score})
        for qs in corr.scores:
            if not qs.question.competence: continue
            comp_name = qs.question.competence.name
            if comp_name not in comp_scores: comp_scores[comp_name] = {}
            comp_scores[comp_name][corr.assignment.title] = qs.score
    competence_stats = []
    for comp_name, scores in comp_scores.items():
        avg = sum(scores.values()) / len(scores) if scores else 0; values = list(scores.values()); trend = values[-1] - values[-2] if len(values) >= 2 else 0
        competence_stats.append({'name': comp_name, 'average': round(avg, 1), 'trend': round(trend, 1), 'scores': scores})
    competence_stats.sort(key=lambda x: x['average'], reverse=True)
    return jsonify({'competences': competence_stats, 'evolution': evolution, 'student_name': student.alias})

@teacher_stats_bp.route('/api/student/<int:student_id>/prediction')
@login_required
def student_prediction(student_id):
    student = Student.query.get_or_404(student_id)
    if student.classroom.teacher_id != current_user.id: return jsonify({'error': 'Non autorisé'}), 403
    corrections = Correction.query.filter_by(student_id=student_id, status='published').order_by(Correction.created_at.desc()).limit(5).all()
    if len(corrections) < 3: return jsonify({'risk': 'insuffisant', 'message': 'Pas assez de données (minimum 3 corrections)', 'color': 'gray'})
    scores = [c.total_score or 0 for c in corrections]; avg_score = sum(scores) / len(scores); last_score = scores[0] if scores else 0
    trend = 0
    if len(scores) >= 2: prev_avg = sum(scores[1:]) / len(scores[1:]); trend = last_score - prev_avg
    if avg_score < 10: risk, message, color = 'élevé', "L'élève a des difficultés persistantes.", 'red'
    elif avg_score < 12:
        if trend < -2: risk, message, color = 'élevé', "Baisse récente préoccupante.", 'orange'
        else: risk, message, color = 'moyen', "Résultats fragiles.", 'orange'
    elif avg_score < 15: risk, message, color = 'faible', "Bonnes performances générales.", 'green'
    else: risk, message, color = 'très faible', "Excellent niveau.", 'green'
    if trend < -3 and avg_score >= 12: risk, message, color = 'moyen', "Baisse récente inhabituelle.", 'orange'
    return jsonify({'risk': risk, 'message': message, 'color': color, 'avg_score': round(avg_score, 1), 'last_score': round(last_score, 1), 'trend': round(trend, 1), 'corrections_count': len(corrections)})