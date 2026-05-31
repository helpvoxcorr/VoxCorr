"""
Service IA — Mistral (mistral-small-latest)
Synthétise la transcription brute du prof en :
  - formatted_text : texte HTML lisible pour l'élève
  - grades         : [{question, score, max_score}]
"""
import os, json, re
from mistralai import Mistral

SYSTEM_PROMPT = """Tu es un assistant pédagogique. Un enseignant t'envoie la transcription brute \
de sa correction orale d'une copie d'élève.

IMPORTANT — format des notes en français oral :
- "3,5" ou "3.5" ou "3h30" ou "trois et demi" = 3,5 points
- "un sur deux" = 1/2  |  "deux sur quatre" = 2/4
- Toujours extraire le nombre réel, jamais un format heure.

Ta mission :
1. Réécrire la correction en français professionnel et structuré.
2. Extraire toutes les notes mentionnées et les associer à la bonne question.

Tu reçois la liste des questions du devoir avec leur position (index 0, 1, 2…).
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

Réponds UNIQUEMENT avec un objet JSON valide :
{
  "formatted_text": "<p>Texte HTML structuré…</p>",
  "grades": [
    {"question_index": 0, "question": "Q1", "score": 3.5, "max_score": 4}
  ]
}

Règles :
- formatted_text : HTML simple uniquement — balises autorisées : section, p, ul, li, strong.
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
- grades : score toujours en nombre décimal (3.5, pas "3h30"). Le score ne peut JAMAIS dépasser le max indiqué entre crochets.
- question_index : position de la question dans la liste fournie (commence à 0).
- Extraction des notes implicites : si le prof dit "je te mets un point", "je mets deux points",
  "tu as tout juste" sans nommer explicitement la question, attribue la note à la question
  dont il vient de parler dans le contexte immédiat.
- Si le prof indique clairement qu'il ne met pas de points ("je ne peux pas te mettre de points",
  "zéro", "aucun point", "tu n'as rien"), attribue le score 0 à la question concernée.
- Si tu ne peux pas identifier la question avec certitude, utilise l'ordre d'apparition.
- Conserve le ton du professeur.
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
    """
    Appelle Mistral et retourne {"formatted_text": "...", "grades": [...]}.
    En cas d'erreur API, retourne un fallback sans planter le thread.
    """
    raw_text = normalize_transcript(raw_text)
    api_key = os.environ.get('MISTRAL_API_KEY')

    if api_key:
        try:
            client = Mistral(api_key=api_key)
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
            response = client.chat.complete(
                model    = 'mistral-small-latest',
                messages = [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user',   'content': user_msg},
                ],
                temperature     = 0.2,
                response_format = {'type': 'json_object'},
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'\s*```$',    '', raw)
            return json.loads(raw)

        except Exception as e:
            print(f'[Mistral] Erreur : {e}')
            return _fallback(raw_text, str(e))
    else:
        return _fallback(raw_text, 'MISTRAL_API_KEY absente')


def _fallback(transcript: str, reason: str) -> dict:
    """Parsing regex basique si Mistral est indisponible."""
    grades = []
    pattern = r'(?:question|q)\s*(\d+[a-z]?)\s*[,:]?\s*([\d.,]+)\s*(?:sur|/|points?|pts?)?\s*([\d.,]+)?'
    for m in re.finditer(pattern, transcript, re.IGNORECASE):
        label     = f'Question {m.group(1)}'
        score     = float(m.group(2).replace(',', '.'))
        max_score = float(m.group(3).replace(',', '.')) if m.group(3) else None
        if not any(g['question'] == label for g in grades):
            grades.append({'question': label, 'score': score, 'max_score': max_score})

    html  = f'<p>{transcript}</p>'
    html += f'<p class="text-muted small">Note : synthèse IA indisponible ({reason}).</p>'
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
    """
    Reformule une appréciation générale dictée oralement.
    Retourne le texte reformulé, ou le texte brut en cas d'erreur.
    """
    raw_text = normalize_transcript(raw_text)
    api_key  = os.environ.get('MISTRAL_API_KEY')
    if not api_key:
        return raw_text
    try:
        client   = Mistral(api_key=api_key)
        response = client.chat.complete(
            model    = 'mistral-small-latest',
            messages = [
                {'role': 'system', 'content': APPRECIATION_PROMPT},
                {'role': 'user',   'content': f"Transcription brute :\n{raw_text}"},
            ],
            temperature     = 0.3,
            response_format = {'type': 'json_object'},
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$',    '', raw)
        return json.loads(raw).get('formatted_text', raw_text)
    except Exception as e:
        print(f'[Mistral appreciation] Erreur : {e}')
        return raw_text