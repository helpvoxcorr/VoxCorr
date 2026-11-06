from types import SimpleNamespace as NS

from app.services.synthesis import clean, build, editor_fields

QS = [NS(label='Définir le terme'), NS(label='Classer')]

AI = ('<section data-qi="intro"><p>Bonjour, voici ton retour.</p></section>'
      '<section data-qi="0"><p class="section-label">Q1 — Définir le terme</p><p>Très bien.</p></section>'
      '<section data-qi="1"><p class="section-label">Q2 — Classer</p><p>Il manque un <strong>argument</strong>.</p></section>'
      '<section data-qi="conclusion"><p>Continue ainsi.</p></section>')


def test_une_synthese_normale_ne_change_pas():
    assert clean(AI) == AI


def test_nettoyage_idempotent():
    messy = '<div><p onclick="x()">Salut <em>toi</em></p><ul><li>un</li><li>deux</li></ul></div>'
    assert clean(clean(messy)) == clean(messy)


def test_scripts_et_attributs_supprimes():
    out = clean('<p>Salut<script>alert(1)</script></p><img src=x onerror=alert(1)><a href="javascript:x()">lien</a>')
    for banni in ('<script', 'alert', 'onerror', '<img', 'javascript', '<a '):
        assert banni not in out
    assert 'Salut' in out


def test_cle_de_section_invalide():
    out = clean('<section data-qi=\'"><script>x\' onclick="y"><p>a</p></section>')
    assert 'onclick' not in out and '<script' not in out
    assert '<p>a</p>' in out


def test_texte_simple_sans_balise():
    assert clean('Un simple texte') == '<p>Un simple texte</p>'


def test_champs_de_l_editeur():
    f = editor_fields(AI, QS)
    assert [x['key'] for x in f] == ['intro', '0', '1', 'conclusion']
    assert f[2]['text'] == 'Il manque un **argument**.'
    assert f[2]['label'] == 'Q2 — Classer'


def test_aller_retour_edition():
    texts = {'intro': 'Salut', '0': 'Bien.', '1': '', 'conclusion': 'Fin'}
    html = build(texts, QS)
    assert '<section data-qi="1">' not in html
    back = {x['key']: x['text'] for x in editor_fields(html, QS)}
    assert back == texts


def test_intitule_vient_du_devoir():
    assert '<p class="section-label">Q1 — Définir le terme</p>' in build({'0': 'Bien.'}, QS)


def test_gras_et_listes():
    html = build({'intro': 'Un **point** clé.\n\n- un\n- deux'}, QS)
    assert '<strong>point</strong>' in html
    assert '<ul><li>un</li><li>deux</li></ul>' in html
    assert editor_fields(html, QS)[0]['text'] == 'Un **point** clé.\n\n- un\n- deux'


def test_texte_saisi_echappe():
    html = build({'intro': '<b>x</b> & "y"'}, QS)
    assert '&lt;b&gt;x&lt;/b&gt; &amp; "y"' in html
    assert '<b>' not in html


def test_note_d_echec_gardee_a_l_affichage_retiree_a_l_edition():
    fail = '<p>Bonjour Adam, 5 sur 5.</p><p class="text-muted small">Note : synthèse IA indisponible (IA indisponible).</p>'
    assert 'synthèse IA indisponible' in clean(fail)
    f = editor_fields(fail, QS)
    assert f[0]['text'] == 'Bonjour Adam, 5 sur 5.'
    assert 'indisponible' not in build({'intro': f[0]['text']}, QS)