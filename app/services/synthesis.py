"""
Synthèse écrite destinée à l'élève : lecture, édition et assainissement.

Format stocké (Correction.structured_text) :
    <section data-qi="intro|0|1|…|conclusion"> [<p class="section-label">Q1 — …</p>] <p>…</p> … </section>
Seules les balises section, p, strong, ul, li (et la note « synthèse IA indisponible ») sont conservées.
Tout le reste, scripts et attributs compris, est supprimé.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

_KEY_RE = re.compile(r'^(intro|conclusion|\d{1,2})$')
MAX_TEXT = 20000


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._cur = None
        self._buf = None     # paragraphe en cours (morceaux de texte)
        self._kind = None    # 'p', 'li', 'label' ou 'note'
        self._drop = 0       # profondeur dans <script> / <style>

    def _block(self):
        if self._cur is None:
            self._cur = {'key': 'texte', 'label': None, 'paras': [], 'notes': []}
            self.blocks.append(self._cur)
        return self._cur

    def _flush(self):
        if self._buf is None:
            return
        text = re.sub(r'\s+', ' ', ''.join(self._buf)).strip()
        text = re.sub(r'\*\*\s*\*\*', '', text)
        kind, self._buf, self._kind = self._kind, None, None
        if not text.replace('*', '').strip():
            return
        block = self._block()
        if kind == 'label':
            block['label'] = text.replace('**', '')
        elif kind == 'note':
            block['notes'].append(text.replace('**', ''))
        elif kind == 'li':
            block['paras'].append('- ' + text)
        else:
            block['paras'].append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self._drop += 1
        elif self._drop:
            return
        elif tag == 'section':
            self._flush()
            key = (a.get('data-qi') or '').strip()
            self._cur = {'key': key if _KEY_RE.match(key) else 'texte', 'label': None, 'paras': [], 'notes': []}
            self.blocks.append(self._cur)
        elif tag in ('p', 'li'):
            self._flush()
            cls = a.get('class') or ''
            if 'section-label' in cls:
                self._kind = 'label'
            elif 'text-muted' in cls:
                self._kind = 'note'
            else:
                self._kind = 'li' if tag == 'li' else 'p'
            self._buf = []
        elif tag in ('strong', 'b'):
            if self._buf is not None:
                self._buf.append('**')
        elif tag == 'br':
            if self._buf is not None:
                self._buf.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._drop = max(0, self._drop - 1)
        elif self._drop:
            return
        elif tag in ('p', 'li'):
            self._flush()
        elif tag in ('strong', 'b'):
            if self._buf is not None:
                self._buf.append('**')
        elif tag == 'section':
            self._flush()
            self._cur = None

    def handle_data(self, data):
        if self._drop:
            return
        if self._buf is None:
            if not data.strip():
                return
            self._buf, self._kind = [], 'p'
        self._buf.append(data)


def parse(html_text):
    """Découpe une synthèse en blocs : [{'key', 'label', 'paras', 'notes'}].
    Le texte hors section est regroupé dans un bloc de clé 'texte', placé en premier."""
    p = _Parser()
    p.feed(html_text or '')
    p.close()
    p._flush()
    blocks, texte = [], None
    for b in p.blocks:
        if not b['paras']:
            continue
        if b['key'] == 'texte':
            if texte is None:
                texte = {'key': 'texte', 'label': None, 'paras': [], 'notes': []}
                blocks.insert(0, texte)
            texte['paras'].extend(b['paras'])
            texte['notes'].extend(b['notes'])
        else:
            blocks.append(b)
    return blocks


def _join(paras):
    """Paragraphes séparés par une ligne vide ; éléments de liste consécutifs sur des lignes voisines."""
    out, prev_item = '', False
    for p in paras:
        item = p.startswith('- ')
        if out:
            out += '\n' if (item and prev_item) else '\n\n'
        out += p
        prev_item = item
    return out


def _inline(text):
    """Texte brut → HTML : tout est échappé, puis **gras** devient <strong>."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escape(text, quote=False))


def _to_html(text):
    parts, para, items = [], [], []

    def flush_para():
        if para:
            parts.append('<p>' + _inline(' '.join(para)) + '</p>')
            para.clear()

    def flush_items():
        if items:
            parts.append('<ul>' + ''.join('<li>' + _inline(i) + '</li>' for i in items) + '</ul>')
            items.clear()

    for raw in (text or '').replace('\r', '').split('\n'):
        line = raw.strip()
        if not line:
            flush_para()
            flush_items()
        elif line.startswith('- '):
            flush_para()
            items.append(line[2:].strip())
        else:
            flush_items()
            para.append(line)
    flush_para()
    flush_items()
    return ''.join(parts)


def clean(html_text):
    """Forme canonique et sûre d'une synthèse (idempotente)."""
    out = []
    for b in parse(html_text):
        body = _to_html(_join(b['paras']))
        notes = ''.join(f'<p class="text-muted small">{escape(n, quote=False)}</p>' for n in b['notes'])
        if b['key'] == 'texte':
            out.append(body + notes)
        else:
            label = f'<p class="section-label">{escape(b["label"], quote=False)}</p>' if b['label'] else ''
            out.append(f'<section data-qi="{b["key"]}">{label}{body}{notes}</section>')
    return ''.join(out)


def clean_markup(value):
    """Filtre Jinja : {{ texte | synth }} remplace {{ texte | safe }}."""
    from markupsafe import Markup
    return Markup(clean(value))


def editor_fields(structured_text, questions):
    """Champs de l'éditeur : Introduction, une section par question, Conclusion.
    Le texte hors section (synthèse IA ratée) est placé dans l'introduction, la note d'échec est retirée."""
    by_key, texte = {}, []
    for b in parse(structured_text):
        if b['key'] == 'texte':
            texte.extend(b['paras'])
        else:
            by_key.setdefault(b['key'], []).extend(b['paras'])
    if texte:
        by_key['intro'] = texte + by_key.get('intro', [])
    fields = [{'key': 'intro', 'label': 'Introduction', 'text': _join(by_key.get('intro', []))}]
    for i, q in enumerate(questions):
        fields.append({'key': str(i), 'label': f'Q{i + 1} — {q.label}', 'text': _join(by_key.get(str(i), []))})
    fields.append({'key': 'conclusion', 'label': 'Conclusion', 'text': _join(by_key.get('conclusion', []))})
    return fields


def build(texts, questions):
    """Reconstruit la synthèse depuis les textes saisis ({'intro': …, '0': …, 'conclusion': …}).
    Les intitulés des questions viennent du devoir, jamais du navigateur."""
    out = []

    def section(key, label, text):
        body = _to_html(text)
        if body:
            lab = f'<p class="section-label">{escape(label, quote=False)}</p>' if label else ''
            out.append(f'<section data-qi="{key}">{lab}{body}</section>')

    section('intro', None, texts.get('intro', ''))
    for i, q in enumerate(questions):
        section(str(i), f'Q{i + 1} — {q.label}', texts.get(str(i), ''))
    section('conclusion', None, texts.get('conclusion', ''))
    return ''.join(out)