import io, base64, os
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer


def make_qr(token: str) -> dict:
    base = os.environ.get('APP_BASE_URL', 'http://localhost:5000')
    url  = f'{base}/c/{token}'

    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=StyledPilImage,
                        module_drawer=RoundedModuleDrawer(),
                        fill_color='#0a0a0a', back_color='#ffffff')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return {'url': url, 'png_b64': f'data:image/png;base64,{b64}'}


def qr_png_bytes(token: str) -> bytes:
    url = f"{os.environ.get('APP_BASE_URL', 'http://localhost:5000')}/c/{token}"
    buf = io.BytesIO()
    qrcode.make(url).save(buf, format='PNG')
    buf.seek(0)
    return buf.read()
