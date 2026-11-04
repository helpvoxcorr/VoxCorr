"""
Niveaux de maîtrise des compétences.

Règle unique, exprimée en part du BARÈME DE LA QUESTION (jamais du total du devoir) :
    0 %                    → maîtrise insuffisante   (rouge)
    de 0 % à 50 % inclus   → maîtrise fragile        (jaune)
    de 50 % à 80 % inclus  → maîtrise satisfaisante  (vert clair)
    au-dessus de 80 %      → très bonne maîtrise     (vert foncé)
    100 %                  → excellente maîtrise     (vert foncé + étoile)

Une évaluation = une question rattachée à une compétence.
Pour une compétence, chaque évaluation compte pour un : on moyenne les pourcentages.
"""
from __future__ import annotations

EPS = 1e-9

# Seuils (part du barème), bornes hautes incluses. Seul endroit à modifier pour les changer.
SEUIL_FRAGILE = 0.50
SEUIL_SATISFAISANT = 0.80
SEUIL_TENDANCE = 0.10      # écart à partir duquel on parle de hausse ou de baisse
MIN_EVALUATIONS = 2        # en dessous : « peu évalué »

LEVELS = {
    'insuffisante':  {'rank': 1, 'label': 'Maîtrise insuffisante',  'color': 'rouge'},
    'fragile':       {'rank': 2, 'label': 'Maîtrise fragile',       'color': 'jaune'},
    'satisfaisante': {'rank': 3, 'label': 'Maîtrise satisfaisante', 'color': 'vert-clair'},
    'tres_bonne':    {'rank': 4, 'label': 'Très bonne maîtrise',    'color': 'vert-fonce'},
}
LABEL_EXCELLENTE = 'Excellente maîtrise'


def ratio(score, max_points):
    """Part du barème obtenue (de 0 à 1), ou None si la note ou le barème est inutilisable.
    Une note hors barème est ramenée dans [0, barème]."""
    if score is None or max_points is None:
        return None
    try:
        score = float(score)
        max_points = float(max_points)
    except (TypeError, ValueError):
        return None
    if max_points <= 0:
        return None
    return min(max(score, 0.0), max_points) / max_points


def level_key(r):
    """Clé du palier pour une part de barème."""
    if r is None:
        return None
    if r <= EPS:
        return 'insuffisante'
    if r <= SEUIL_FRAGILE + EPS:
        return 'fragile'
    if r <= SEUIL_SATISFAISANT + EPS:
        return 'satisfaisante'
    return 'tres_bonne'


def describe(r):
    """Palier d'une part de barème : clé, libellé, couleur, étoile (excellente maîtrise)."""
    key = level_key(r)
    if key is None:
        return None
    info = dict(LEVELS[key])
    info['key'] = key
    info['star'] = r >= 1 - EPS
    if info['star']:
        info['label'] = LABEL_EXCELLENTE
    return info


def summarize(ratios):
    """Synthèse d'une compétence à partir des parts de barème de toutes ses évaluations,
    dans l'ordre chronologique. Les valeurs None sont ignorées."""
    values = [r for r in ratios if r is not None]
    if not values:
        return None
    mean = sum(values) / len(values)
    recent = values[-3:]
    trend = None
    if len(recent) >= 2:
        delta = recent[-1] - sum(recent[:-1]) / len(recent[:-1])
        trend = 'hausse' if delta > SEUIL_TENDANCE else 'baisse' if delta < -SEUIL_TENDANCE else 'stable'
    return {
        'count': len(values),
        'mean': mean,
        'percent': int(mean * 100 + 0.5),
        'on4': round(mean * 4, 1),
        'level': describe(mean),
        'few_data': len(values) < MIN_EVALUATIONS,
        'trend': trend,
        'last': values[-1],
    }