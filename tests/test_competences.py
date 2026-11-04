import pytest
from app.services.competences import ratio, describe, summarize


@pytest.mark.parametrize('score, maxi, key, star', [
    # question sur 4
    (0, 4, 'insuffisante', False),
    (1, 4, 'fragile', False),
    (2, 4, 'fragile', False),
    (3, 4, 'satisfaisante', False),
    (4, 4, 'tres_bonne', True),
    # question sur 20 (ta grille)
    (0, 20, 'insuffisante', False),
    (1, 20, 'fragile', False),
    (10, 20, 'fragile', False),
    (11, 20, 'satisfaisante', False),
    (16, 20, 'satisfaisante', False),
    (17, 20, 'tres_bonne', False),
    (20, 20, 'tres_bonne', True),
    # question sur 1 : réussie ou ratée
    (0, 1, 'insuffisante', False),
    (1, 1, 'tres_bonne', True),
    # question sur 5 et sur 8
    (2.5, 5, 'fragile', False),
    (3, 5, 'satisfaisante', False),
    (4, 5, 'satisfaisante', False),
    (5, 5, 'tres_bonne', True),
    (6.4, 8, 'satisfaisante', False),
    (6.5, 8, 'tres_bonne', False),
    # demi-points
    (0.5, 4, 'fragile', False),
    (2.5, 4, 'satisfaisante', False),
    # notes hors barème : ramenées dans l'intervalle
    (5, 4, 'tres_bonne', True),
    (-1, 4, 'insuffisante', False),
])
def test_palier_d_une_evaluation(score, maxi, key, star):
    d = describe(ratio(score, maxi))
    assert d['key'] == key
    assert d['star'] is star


def test_donnees_inutilisables():
    assert ratio(None, 4) is None
    assert ratio(3, None) is None
    assert ratio(3, 0) is None
    assert ratio('abc', 4) is None
    assert describe(None) is None


def test_exemple_pratiquer_des_langages():
    s = summarize([ratio(5, 5), ratio(4, 8)])
    assert s['count'] == 2
    assert s['percent'] == 75
    assert s['on4'] == 3.0
    assert s['level']['key'] == 'satisfaisante'


def test_moyenne_de_deux_baremes_differents():
    s = summarize([ratio(3, 4), ratio(4, 6)])
    assert s['percent'] == 71
    assert s['on4'] == 2.8
    assert s['level']['key'] == 'satisfaisante'


def test_cinquante_pour_cent_pile_est_fragile():
    s = summarize([ratio(0, 4), ratio(4, 4)])
    assert s['level']['key'] == 'fragile'


def test_excellente_exige_toutes_les_evaluations_a_100_pour_cent():
    assert summarize([ratio(5, 5), ratio(7, 7)])['level']['star'] is True
    assert summarize([ratio(5, 5), ratio(6, 7)])['level']['star'] is False


def test_peu_evalue():
    assert summarize([ratio(3, 4)])['few_data'] is True
    assert summarize([ratio(3, 4), ratio(3, 4)])['few_data'] is False


def test_tendance():
    assert summarize([ratio(4, 4), ratio(4, 4), ratio(2, 4)])['trend'] == 'baisse'
    assert summarize([ratio(1, 4), ratio(2, 4), ratio(4, 4)])['trend'] == 'hausse'
    assert summarize([ratio(2, 4), ratio(2, 4), ratio(2, 4)])['trend'] == 'stable'
    assert summarize([ratio(2, 4)])['trend'] is None


def test_rien_a_resumer():
    assert summarize([]) is None
    assert summarize([None, None]) is None