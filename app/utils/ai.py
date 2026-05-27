import os
import json
from groq import Groq

def process_correction_with_ai(raw_text):
    # Initialisation du client Groq avec la clé du .env
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    system_prompt = """Tu es un assistant pédagogique expert. 
    On te donne la transcription brute (souvent mal ponctuée et avec des hésitations orales) d'un professeur qui corrige une copie.
    
    Ta mission :
    1. Réécrire cette correction dans un français parfait, professionnel, bien ponctué et structuré en paragraphes. Retire les hésitations orales ("euh", "ben", les répétitions).
    2. Extraire toutes les notes mentionnées (ex: "Question 1, 3 sur 5") pour en faire un tableau.
    
    Tu DOIS OBLIGATOIREMENT répondre UNIQUEMENT avec un objet JSON valide ayant cette structure exacte :
    {
        "formatted_text": "Le texte propre et structuré de la correction...",
        "grades": [
            {"question": "Nom de la question ou compétence", "score": 3, "max_score": 5}
        ]
    }
    Ne rajoute aucun texte avant ou après le JSON.
    """

    try:
        # Appel au modèle Llama 3 (très rapide et excellent en français)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text}
            ],
            model="llama-3.1-70b-versatile",
            temperature=0.2, # Température basse pour rester factuel
            response_format={"type": "json_object"} # Force le format JSON
        )
        
        # Récupération et conversion de la réponse JSON
        result_string = chat_completion.choices[0].message.content
        return json.loads(result_string)
        
    except Exception as e:
        print(f"Erreur IA Groq : {e}")
        return None