from types import SimpleNamespace as NS

from app.blueprints.teacher_corrections import _synth_failed


def corr(status, raw, text):
    return NS(status=status, raw_transcript=raw, structured_text=text)


def test_synthese_a_refaire():
    note = '<p>Brut</p><p class="text-muted small">Note : synthèse IA indisponible (x).</p>'
    assert _synth_failed(corr('draft', 'dictée', note))
    assert _synth_failed(corr('draft', 'dictée', ''))
    assert not _synth_failed(corr('draft', 'dictée', '<section data-qi="intro"><p>ok</p></section>'))
    assert not _synth_failed(corr('published', 'dictée', note))
    assert not _synth_failed(corr('processing', 'dictée', note))
    assert not _synth_failed(corr('absent', None, ''))
    assert not _synth_failed(corr('draft', '', ''))
    assert not _synth_failed(None)