"""
Service IA — Mistral (mistral-small-latest)
Synthétise la transcription brute du prof en :
  - formatted_text : texte HTML lisible pour l'élève
  - grades         : [{question, score, max_score}]
"""
import os, json, re, tempfile
from mistralai import Mistral
import time

LLM_ORDER = [p.strip() for p in os.environ.get('LLM_ORDER', 'mistral,agnes,gemini').split(',') if p.strip()]
LLM_TIMEOUT = 30  # secondes max par fournisseur


def _call_mistral(system_prompt, user_msg, temperature):
    client = Mistral(api_key=os.environ['MISTRAL_API_KEY'], timeout_ms=LLM_TIMEOUT * 1000)
    r = client.chat.complete(
        model=os.environ.get('MISTRAL_MODEL', 'mistral-small-latest'),
        messages=[{'role': 'system', 'content': system_prompt},
                  {'role': 'user', 'content': user_msg}],
        temperature=temperature,
        response_format={'type': 'json_object'},
    )
    return r.choices[0].message.content


def _call_agnes(system_prompt, user_msg, temperature):
    import requests
    r = requests.post(
        'https://apihub.agnes-ai.com/v1/chat/completions',
        headers={'Authorization': 'Bearer ' + os.environ['AGNES_API_KEY']},
        json={
            'model': os.environ.get('AGNES_MODEL', 'agnes-2.0-flash'),
            'messages': [{'role': 'system', 'content': system_prompt},
                         {'role': 'user', 'content': user_msg}],
            'temperature': temperature,
            'response_format': {'type': 'json_object'},
        },
        timeout=LLM_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f'{r.status_code} {r.text[:300]}')
    return r.json()['choices'][0]['message']['content']


GEMINI_MODELS = [m.strip() for m in os.environ.get(
    'GEMINI_MODELS', 'gemini-3.8-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite'
).split(',') if m.strip()]


def _call_gemini(system_prompt, user_msg, temperature):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    last = None
    for model in GEMINI_MODELS:
        for attempt in range(2):
            try:
                r = client.models.generate_content(
                    model=model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                        response_mime_type='application/json',
                        http_options=types.HttpOptions(timeout=LLM_TIMEOUT * 1000),
                    ),
                    contents=user_msg,
                )
                return r.text
            except Exception as e:
                last = e
                print(f'[IA] gemini/{model} essai {attempt + 1} échec : {str(e)[:100]}', flush=True)
                time.sleep(3)
    raise last


_PROVIDERS = {
    'mistral': ('MISTRAL_API_KEY', _call_mistral),
    'agnes':   ('AGNES_API_KEY',   _call_agnes),
    'gemini':  ('GEMINI_API_KEY',  _call_gemini),
}


def _call_llm(system_prompt, user_msg, temperature):
    """Essaie chaque fournisseur dans l'ordre, renvoie le premier JSON valide."""
    last_error = None
    for name in LLM_ORDER:
        entry = _PROVIDERS.get(name)
        if not entry or not os.environ.get(entry[0]):
            continue
        t0 = time.time()
        try:
            text = entry[1](system_prompt, user_msg, temperature).strip()
            text = re.sub(r'^```json\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            data = json.loads(text)
            print(f'[IA] {name} OK en {time.time() - t0:.1f}s', flush=True)
            return data
        except Exception as e:
            last_error = e
            print(f'[IA] {name} échec après {time.time() - t0:.1f}s : {e}', flush=True)
    raise last_error or RuntimeError('Aucune clé IA configurée')

SYSTEM_PROMPT = """Tu es un assistant pédagogique. Un enseignant t'envoie la transcription brute \
de sa correction orale d'une copie d'élève.

IMPORTANT — format des notes en français oral :
- "3,5" ou "3.5" ou "3h30" ou "trois et demi" = 3,5 points
- "un sur deux" = 1/2  |  "deux sur quatre" = 2/4
- Toujours extraire le nombre réel, jamais un format heure.

Tu reçois la liste des questions du devoir avec leur label et leur note maximale.
L'enseignant peut les corriger dans n'importe quel ordre à l'oral.
Tu dois identifier à quelle question chaque note correspond, en te basant sur le nom
ou le numéro mentionné à l'oral ("question 2", "Q2", "deuxième question", etc.).

RÈGLES D'IDENTIFICATION DES QUESTIONS — priorité décroissante :
1. Numéro explicite : "question 1", "Q1", "la première question" avec un chiffre → question_index = chiffre - 1.
2. Ordinal ambigu : "ta première réponse", "le premier point" SANS chiffre → utilise le max_points
   de la question pour confirmer. Si le prof dit "deux points" et que seule Q1 a max=2.0, c'est Q1.
3. Ordre d'apparition : si aucun numéro ni indice de max ne permet d'identifier, attribue
   dans l'ordre d'apparition dans le transcript (premier commentaire → index 0, etc.).
4. Ne jamais réordonner les sections dans formatted_text : respecte toujours l'ordre
   question_index 0, 1, 2… quelle que soit l'ordre oral du prof.

Pour chaque question identifiée, tu dois :
- Attribuer une note (score) sur la base des commentaires du professeur.
- Identifier la compétence évaluée (parmi : Rédaction, Orthographe, Grammaire, Calcul, Raisonnement, Analyse, Synthèse, ou une autre pertinente si non listée).
- Fournir un conseil personnalisé (une phrase courte) pour aider l'élève à progresser. Si aucun conseil n'est donné, mets une chaîne vide.

Réponds UNIQUEMENT avec un objet JSON valide :
{
  "formatted_text": "<p>Texte HTML structuré…</p>",
  "grades": [
    {
      "question_index": 0,
      "question": "Q1",
      "score": 3.5,
      "max_score": 4,
      "competence": "Calcul",
      "advice": "Revois les tables de multiplication."
    }
  ]
}

Règles supplémentaires pour formatted_text :
- HTML simple uniquement — balises autorisées : section, p, ul, li, strong.
- Structure le formatted_text en blocs <section> :
  • Remarques générales avant la première question → <section data-qi="intro">…</section>
  • Commentaire de chaque question N → <section data-qi="N">…</section>  (N = question_index, commence à 0)
    Commence chaque section question par un paragraphe avec la classe "section-label" contenant
    le numéro et le label réel de la question.
    Exemple : si question_index=0 et label="Raisonner", écrire :
    <p class="section-label">Q1 — Raisonner</p>
    Exemple : si question_index=2 et label="Distinguer croyance et fait scientifique", écrire :
    <p class="section-label">Q3 — Distinguer croyance et fait scientifique</p>
  • Conclusion éventuelle → <section data-qi="conclusion">…</section>
  • Omets les sections vides.
  • Les sections doivent toujours apparaître dans l'ordre croissant des question_index,
    indépendamment de l'ordre oral du prof.
- formatted_text ne doit pas contenir les notes ni les conseils (ils sont dans grades).
- Extraction des notes implicites : si le prof dit "je te mets un point", "je mets deux points",
  "tu as tout juste" sans nommer explicitement la question, attribue la note à la question
  dont il vient de parler dans le contexte immédiat.
- Si le prof indique clairement qu'il ne met pas de points ("je ne peux pas te mettre de points",
  "zéro", "aucun point", "tu n'as rien"), attribue le score 0 à la question concernée.
- Si tu ne peux pas identifier la question avec certitude, utilise l'ordre d'apparition.
- Conserve le ton du professeur.

Pour les grades :
- score : nombre décimal (3.5, pas "3h30"). Ne dépasse jamais max_score.
- question_index : position de la question dans la liste fournie (commence à 0).
- competence : chaîne de caractères (ex: "Rédaction", "Calcul").
- advice : phrase courte, ou chaîne vide.
"""

def normalize_transcript(text: str) -> str:
    """
    Corrige les artifacts fréquents de la Web Speech API en français.
    "3h30" → "3,5"  |  "2h30" → "2,5"  |  "1h30" → "1,5" etc.
    """
    text = re.sub(r'(\d+)h30', lambda m: f"{m.group(1)},5", text)
    text = re.sub(r'(\d+)h00', lambda m: m.group(1), text)
    text = re.sub(r'(\d+)\s+et\s+demi', lambda m: f"{m.group(1)},5", text)
    text = text.replace(' virgule ', ',')
    return text

def synthesize_with_mistral(raw_text: str, question_labels: list[str], question_max: list[float] | None = None) -> dict:
    """Appelle l'IA (chaîne de fournisseurs) et retourne {"formatted_text": ..., "grades": [...]}."""
    raw_text = normalize_transcript(raw_text)
    labels_str = ', '.join(
        f"Q{i+1} (index {i}, label:\"{lbl}\") [max {question_max[i]}]"
        if question_max else
        f"Q{i+1} (index {i}, label:\"{lbl}\")"
        for i, lbl in enumerate(question_labels)
    )
    user_msg = (
        f"Questions du devoir (index : label [max points]) : {labels_str}\n\n"
        f"Transcription brute :\n{raw_text}"
    )
    try:
        return _call_llm(SYSTEM_PROMPT, user_msg, 0.2)
    except Exception as e:
        print(f'[IA] Tous les fournisseurs ont échoué : {e}', flush=True)
        return _fallback(raw_text, 'IA indisponible', question_max)


def _fallback(transcript: str, reason: str, question_max=None) -> dict:
    """Secours sans IA : repère « 5 sur 5 », « 3 points sur 8 »… et les rattache aux questions par leur barème."""
    grades, used = [], set()
    pattern = r'(\d+(?:[.,]\d+)?)\s*(?:points?|pts?)?\s*sur\s*(\d+(?:[.,]\d+)?)'
    for m in re.finditer(pattern, transcript, re.IGNORECASE):
        score = float(m.group(1).replace(',', '.'))
        mx = float(m.group(2).replace(',', '.'))
        idx = None
        for i, q in enumerate(question_max or []):
            if i not in used and abs(float(q) - mx) < 0.01:
                idx = i
                break
        if idx is None:
            continue
        used.add(idx)
        grades.append({'question_index': idx, 'question': f'Q{idx + 1}', 'score': min(score, mx),
                       'max_score': mx, 'competence': '', 'advice': ''})
    html = (f'<p>{transcript}</p><p class="text-muted small">Note : synthèse IA indisponible ({reason}). '
            f'Utilisez « Regénérer la synthèse » plus tard.</p>')
    return {'formatted_text': html, 'grades': grades}


APPRECIATION_PROMPT = """Tu es un assistant pédagogique. Un enseignant t'envoie la transcription \
brute de son appréciation orale sur l'ensemble d'une classe.

Ta mission : réécrire cette appréciation en français professionnel, bienveillant et structuré, \
en t'adressant à la classe entière (ton collectif, pas individuel).

Réponds UNIQUEMENT avec un objet JSON valide :
{
  "formatted_text": "<p>Première idée.</p><p>Deuxième idée.</p>"
}

Règles :
- HTML simple uniquement : balises <p> pour chaque idée distincte, <strong> pour insister.
- Regroupe les idées par thème dans des paragraphes séparés.
- Conserve le sens et le ton du professeur.
- Corrige la ponctuation et l'orthographe.
- 2 à 4 paragraphes maximum.
"""

def synthesize_appreciation(raw_text: str) -> str:
    """Reformule l'appréciation en texte simple (paragraphes séparés par une ligne vide).
    Lève une exception si l'IA est indisponible."""
    raw_text = normalize_transcript(raw_text)
    data = _call_llm(APPRECIATION_PROMPT, f"Transcription brute :\n{raw_text}", 0.3)
    html = data.get('formatted_text') or ''
    text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', html)
    text = re.sub(r'<[^>]+>', '', text).strip()
    if not text:
        raise RuntimeError('Réponse IA vide')
    return text


def transcribe_with_mistral(audio_bytes: bytes, filename: str = 'audio.webm') -> str:
    """
    Transcrit un fichier audio en texte via l'API de transcription Mistral (Voxtral).
    Utilisée en fallback pour les navigateurs sans Web Speech API (ex. Firefox).

    Args:
        audio_bytes : contenu brut du fichier audio.
        filename    : nom de fichier — l'extension sert à Mistral pour le format.

    Returns:
        Le texte transcrit. Lève une exception si MISTRAL_API_KEY est absente
        ou si l'appel échoue, à charge de l'appelant de gérer le cas (l'audio
        est généralement déjà sauvegardé côté appelant avant la transcription).
    """
    api_key = os.environ.get('MISTRAL_API_KEY')
    if not api_key:
        raise RuntimeError('MISTRAL_API_KEY absente')

    suffix = '.' + filename.rsplit('.', 1)[-1] if '.' in filename else '.webm'

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        client = Mistral(api_key=api_key)
        with open(tmp_path, 'rb') as f:
            result = client.audio.transcriptions.complete(
                model    = 'voxtral-mini-latest',
                file     = {'content': f, 'file_name': filename},
                language = 'fr',
            )
        return result.text
    except Exception as e:
        print(f'[Mistral transcribe] Erreur : {e}')
        raise
    finally:
        os.unlink(tmp_path)