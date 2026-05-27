"""
Service stockage audio — Cloudinary.
La config est initialisée à chaque appel depuis les variables d'env.
"""
import os
import cloudinary
import cloudinary.uploader


def _configure():
    """Initialise le SDK Cloudinary depuis les variables d'env."""
    cloudinary.config(
        cloud_name  = os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key     = os.environ.get('CLOUDINARY_API_KEY'),
        api_secret  = os.environ.get('CLOUDINARY_API_SECRET'),
        secure      = True,
    )


def upload_audio(file_bytes: bytes, public_id: str, teacher_id: int) -> dict:
    """
    Upload un blob audio sur Cloudinary.
    Retourne {"url": ..., "duration": ..., "public_id": ...}
    """
    _configure()
    result = cloudinary.uploader.upload(
        file_bytes,
        public_id     = public_id,
        folder        = f'voxcorr/{teacher_id}',
        resource_type = 'video',   # obligatoire pour l'audio sur Cloudinary
        format        = 'mp3',
        overwrite     = True,
    )
    return {
        'url':       result.get('secure_url'),
        'duration':  result.get('duration'),
        'public_id': result.get('public_id'),
    }


def delete_audio(public_id: str):
    _configure()
    cloudinary.uploader.destroy(public_id, resource_type='video')
