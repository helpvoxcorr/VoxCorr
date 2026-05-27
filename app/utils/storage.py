import cloudinary
import cloudinary.uploader
import os

def upload_audio_to_cloudinary(file_stream):
    try:
        # resource_type="video" est obligatoire pour l'audio sur Cloudinary
        response = cloudinary.uploader.upload(
            file_stream, 
            resource_type="video",
            folder="voxcorr_audio"
        )
        return response.get('secure_url')
    except Exception as e:
        print(f"Erreur Cloudinary : {e}")
        return None