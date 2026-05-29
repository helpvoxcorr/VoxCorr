"""
Service email — SendGrid
Envoie le mail de vérification de compte.
"""
import os
from flask import current_app


def send_verification_email(to_email: str, first_name: str, token: str) -> bool:
    """
    Envoie un email de vérification via SendGrid.
    Retourne True si envoyé, False sinon.
    """
    api_key = current_app.config.get('SENDGRID_API_KEY')
    if not api_key:
        current_app.logger.warning('[email] SENDGRID_API_KEY absent — email non envoyé')
        return False

    base_url    = current_app.config.get('APP_BASE_URL', 'http://localhost:5000')
    verify_url  = f"{base_url}/auth/verify/{token}"
    from_email  = current_app.config.get('SENDGRID_FROM_EMAIL', 'help.voxcorr@gmail.com')
    from_name   = current_app.config.get('SENDGRID_FROM_NAME',  'VoxCorr Team')

    subject = "Confirmez votre adresse email — VoxCorr"
    html    = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:520px;margin:auto;padding:32px">
      <h2 style="color:#111">Bienvenue sur VoxCorr, {first_name} !</h2>
      <p style="color:#444">Cliquez sur le bouton ci-dessous pour confirmer votre adresse email
         et activer votre compte.</p>
      <a href="{verify_url}"
         style="display:inline-block;margin:24px 0;padding:14px 28px;
                background:#39FF14;color:#000;font-weight:700;border-radius:8px;
                text-decoration:none;font-size:1rem">
        Confirmer mon email
      </a>
      <p style="color:#888;font-size:.85rem">
        Ce lien expire dans 24h. Si vous n'avez pas créé de compte VoxCorr,
        ignorez cet email.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
      <p style="color:#bbb;font-size:.75rem;text-align:center">
        VoxCorr · Correction audio intelligente des copies
      </p>
    </div>
    """

    try:
        import urllib.request, urllib.error, json
        payload = json.dumps({
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email, "name": from_name},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
        }).encode()

        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data    = payload,
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            method = "POST",
        )
        with urllib.request.urlopen(req) as resp:
            current_app.logger.info(f'[email] Envoyé à {to_email} — status {resp.status}')
            return True

    except Exception as e:
        current_app.logger.error(f'[email] Erreur SendGrid : {e}')
        return False