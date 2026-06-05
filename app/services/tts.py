import asyncio
import edge_tts

VOICE = "fr-FR-DeniseNeural"  # voix féminine française

async def _generate_audio(text: str, output_file: str):
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_file)

def generate_tts_audio(text: str) -> bytes:
    """
    Génère un fichier audio MP3 à partir du texte, retourne les bytes.
    Utilise Edge TTS (gratuit, sans clé).
    """
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        asyncio.run(_generate_audio(text, tmp_path))
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)