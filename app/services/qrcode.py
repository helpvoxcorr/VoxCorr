import io, base64, os, logging
import qrcode

log = logging.getLogger(__name__)


def public_base_url() -> str:
    """Adresse publique du site, sans slash final."""
    base = os.environ.get('APP_BASE_URL', '').strip().rstrip('/')
    if not base:
        base = 'http://localhost:5000'
        log.warning("APP_BASE_URL n'est pas définie : les QR codes pointent vers localhost.")
    elif 'localhost' in base or '127.0.0.1' in base or 'ngrok' in base:
        log.warning("APP_BASE_URL (%s) est une adresse locale ou temporaire : "
                    "ne pas imprimer de QR codes avec elle.", base)
    return base


def _qr_image(url: str):
    qr = qrcode.QRCode(version=None,
                       error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color='#0a0a0a', back_color='#ffffff')


def make_qr(token: str) -> dict:
    url = f'{public_base_url()}/c/{token}'
    buf = io.BytesIO()
    _qr_image(url).save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {'url': url, 'png_b64': f'data:image/png;base64,{b64}'}


def qr_png_bytes(token: str) -> bytes:
    buf = io.BytesIO()
    _qr_image(f'{public_base_url()}/c/{token}').save(buf, format='PNG')
    return buf.getvalue()