"""Suivi des compétences : agrège les notes déjà enregistrées (aucune table dédiée)."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date

from app.extensions import db
from app.models import Assignment, Competence, Correction, Question, QuestionScore
from app.services.competences import SEUIL_FRAGILE, SEUIL_SATISFAISANT, describe, ratio, summarize

COUNTED = ('draft', 'published')      # copies prises en compte (pas les absents, pas les analyses en cours)
FAIL_MARK = 'synthèse IA indisponible'

DOMAINS = {
    'D1': 'Les langages pour penser et communiquer',
    'D2': 'Les méthodes et outils pour apprendre',
    'D3': 'La formation de la personne et du citoyen',
    'D4': 'Les systèmes naturels et les systèmes techniques',
    'D5': "Les représentations du monde et l'activité humaine",
}


def legend():
    return {'fragile': int(round(SEUIL_FRAGILE * 100)), 'satisfaisant': int(round(SEUIL_SATISFAISANT * 100))}


def fr_filter(value, digits=None):
    """Nombre à la française : 2,5 / 4 / 2,8 (filtre Jinja « fr »)."""
    if value is None:
        return '—'
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = ('%.*f' % (digits, x)) if digits is not None else ('%g' % round(x, 2))
    return text.replace('.', ',')


def _evaluations(student_ids):
    """{id élève: [évaluations dans l'ordre chronologique]}. Une évaluation = une note de question rattachée à une compétence."""
    out = {sid: [] for sid in student_ids}
    if not out:
        return out
    rows = (db.session.query(QuestionScore, Question, Competence, Assignment, Correction)
            .join(Correction, QuestionScore.correction_id == Correction.id)
            .join(Question, QuestionScore.question_id == Question.id)
            .join(Competence, Question.competence_id == Competence.id)
            .join(Assignment, Question.assignment_id == Assignment.id)
            .filter(Correction.student_id.in_(list(out)), Correction.status.in_(COUNTED))
            .all())
    for qs, q, comp, a, corr in rows:
        if corr.status == 'draft' and (not corr.structured_text or FAIL_MARK in corr.structured_text):
            continue   # analyse ratée : notes non fiables
        r = ratio(qs.score, q.max_points)
        if r is None:
            continue
        out[corr.student_id].append({
            'competence_id': comp.id, 'name': comp.name, 'domain': comp.domain or '',
            'ratio': r, 'score': qs.score, 'max': q.max_points,
            'date': a.date or (a.created_at.date() if a.created_at else None),
            'assignment': a.title, 'assignment_id': a.id, 'order': q.order or 0,
        })
    for evals in out.values():
        evals.sort(key=lambda e: (e['date'] or date.min, e['assignment_id'], e['order']))
    return out


def _group(evals):
    """Regroupe les évaluations par compétence et calcule le palier de chacune."""
    groups = OrderedDict()
    for e in evals:
        g = groups.setdefault(e['competence_id'], {'id': e['competence_id'], 'name': e['name'],
                                                   'domain': e['domain'], 'evals': []})
        e['level'] = describe(e['ratio'])
        g['evals'].append(e)
    result = list(groups.values())
    for g in result:
        g['summary'] = summarize([e['ratio'] for e in g['evals']])
    result.sort(key=lambda g: (g['domain'] or 'Z', g['name'].lower()))
    return result


def student_summary(student_id):
    return _group(_evaluations([student_id])[student_id])


def by_domain(groups):
    out = OrderedDict()
    for g in groups:
        out.setdefault(g['domain'], []).append(g)
    return [{'code': code, 'title': DOMAINS.get(code, 'Sans domaine'), 'groups': gs} for code, gs in out.items()]


def class_matrix(student_ids):
    """(colonnes, {id élève: {id compétence: groupe}}) pour le tableau de la classe."""
    per_student, comps = {}, {}
    for sid, evals in _evaluations(student_ids).items():
        groups = _group(evals)
        per_student[sid] = {g['id']: g for g in groups}
        for g in groups:
            comps.setdefault(g['id'], {'id': g['id'], 'name': g['name'], 'domain': g['domain']})
    columns = sorted(comps.values(), key=lambda c: (c['domain'] or 'Z', c['name'].lower()))
    return columns, per_student