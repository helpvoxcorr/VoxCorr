from app.services.suivi import by_domain, fr_filter


def test_format_francais():
    assert fr_filter(2.5) == '2,5'
    assert fr_filter(4.0) == '4'
    assert fr_filter(2.8333, 1) == '2,8'
    assert fr_filter(4.0, 1) == '4,0'
    assert fr_filter(None) == '—'


def test_regroupement_par_domaine():
    groupes = [{'domain': 'D4', 'name': 'a'}, {'domain': 'D1', 'name': 'b'},
               {'domain': '', 'name': 'c'}, {'domain': 'D4', 'name': 'd'}]
    out = by_domain(groupes)
    assert [d['code'] for d in out] == ['D4', 'D1', '']
    assert len(out[0]['groups']) == 2
    assert out[0]['title'].startswith('Les systèmes naturels')
    assert out[2]['title'] == 'Sans domaine'