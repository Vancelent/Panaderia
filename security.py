from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

SECRET_KEY = "panaderia_secreta_super_segura_no_usar_en_prod"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480 # 8 horas (un turno completo)
import bcrypt

def get_password_hash(password: str) -> str:
    # Genera un salt y hashea el password usando bcrypt nativo
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Compara el password en texto plano con el hash de la BD
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        # Esto ocurre si el string en la DB no es un hash de bcrypt válido
        return False

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
