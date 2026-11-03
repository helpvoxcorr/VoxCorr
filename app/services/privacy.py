"""Retire le nom de l'élève du texte envoyé aux services d'IA, puis le remet dans le résultat."""
import re
import html
import unicodedata

TOKEN_FIRST = 'PRENOM_ELEVE'
TOKEN_LAST = 'NOM_ELEVE'
_PARTICLES = {'de', 'du', 'des', 'la', 'le', 'les', 'van', 'von', 'der', 'den', 'el', 'al', 'ben', 'bin'}
_TOKEN_RE = re.compile(r'\b(PRENOM|NOM)[ _\-]?[EÉ]L[EÈ]VE\b', re.IGNORECASE)


def _fold(s):
    """Texte en minuscules sans accents, de même longueur que l'original."""
    out = []
    for ch in s:
        d = unicodedata.normalize('NFD', ch)
        base = d[0] if d else ch
        low = base.lower()
        out.append(low if len(low) == 1 else base)
    return ''.join(out)


def _parts(name):
    name = (name or '').strip()
    if len(name) < 2 or name in ('—', '-'):
        return []
    parts = {name}
    for p in re.split(r"[\s'’\-]+", name):
        if len(p) >= 3 and _fold(p) not in _PARTICLES:
            parts.add(p)
    return list(parts)


def redact(text, first, last):
    """Remplace le prénom et le nom (casse et accents indifférents) par des jetons neutres."""
    if not text:
        return text
    targets = [(p, TOKEN_FIRST) for p in _parts(first)] + [(p, TOKEN_LAST) for p in _parts(last)]
    if not targets:
        return text
    folded = _fold(text)
    found = []
    for name, token in targets:
        pattern = r'(?<![^\W\d_])' + re.escape(_fold(name)) + r'(?![^\W\d_])'
        for m in re.finditer(pattern, folded):
            found.append((m.start(), m.end(), token))
    found.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    out, pos = [], 0
    for start, end, token in found:
        if start < pos:
            continue
        out.append(text[pos:start])
        out.append(token)
        pos = end
    out.append(text[pos:])
    return ''.join(out)


def restore(text, first, last, html_mode=False):
    """Remet le prénom et le nom à la place des jetons."""
    if not text:
        return text
    esc = (lambda s: html.escape(s or '', quote=False)) if html_mode else (lambda s: s or '')
    return _TOKEN_RE.sub(lambda m: esc(first) if m.group(1).upper() == 'PRENOM' else esc(last), text)


def restore_result(result, first, last):
    if not isinstance(result, dict):
        return result
    if isinstance(result.get('formatted_text'), str):
        result['formatted_text'] = restore(result['formatted_text'], first, last, html_mode=True)
    for g in result.get('grades') or []:
        if isinstance(g, dict):
            for key in ('advice', 'competence', 'question'):
                if isinstance(g.get(key), str):
                    g[key] = restore(g[key], first, last)
    return result