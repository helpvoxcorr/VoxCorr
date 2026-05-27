"""
Anonymisation RGPD.
- Alias mnémotechnique : Animal-NN  ex: Renard-07
- Nom réel chiffré avec Fernet (AES-128) en base de données
"""
import os, hashlib
from cryptography.fernet import Fernet

ANIMALS = [
    'Aigle','Bison','Castor','Dauphin','Élan','Faucon','Gazelle','Hermine',
    'Ibis','Jaguar','Koala','Lièvre','Manchot','Narval','Oryx','Panda',
    'Quetzal','Renard','Serpent','Toucan','Vison','Wapiti','Yak','Zèbre',
    'Albatros','Blaireau','Coyote','Dingo','Épervier','Fouine','Gerfaut',
    'Hibou','Impala','Lynx','Mouflon','Nautile','Ocelot','Puma','Tatou',
]


def _fernet() -> Fernet:
    key = os.environ.get('ENCRYPTION_KEY')
    if not key:
        raise RuntimeError('ENCRYPTION_KEY absente dans .env')
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_name(name: str) -> str:
    return _fernet().encrypt(name.encode()).decode()


def decrypt_name(token: str) -> str:
    if not token:
        return '—'
    return _fernet().decrypt(token.encode()).decode()


def generate_alias(first_name: str, last_name: str, student_number: int) -> str:
    """
    Déterministe : même élève → même alias.
    Le prof reconnaît son élève, mais l'export ne contient que l'alias.
    """
    seed  = f'{first_name.lower()}{last_name.lower()}'
    idx   = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(ANIMALS)
    return f'{ANIMALS[idx]}-{str(student_number).zfill(2)}'
