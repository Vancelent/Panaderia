"""Google simulado para los tests: un par de claves RSA propio firma los id_token, y el servidor los valida
como lo haría con el JWKS de Google, sin salir a Internet."""

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

CLIENT_ID = "123-web.apps.googleusercontent.com"
CLIENT_ANDROID = "123-android.apps.googleusercontent.com"
CLIENT_IOS = "123-ios.apps.googleusercontent.com"
CLAVE_GOOGLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)

ENTORNO = {
    "GOOGLE_CLIENT_ID": CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": "secreto-de-google",
    "OAUTH_REDIRECT_URL": "http://testserver/api/v1/auth/google/callback",
    "GOOGLE_CLIENT_IDS_MOVIL": f"{CLIENT_ANDROID}, {CLIENT_IOS}",
}


def id_token(*, sub="g-1", email="ana@gmail.com", nonce, aud=CLIENT_ID, verificado=True, hd=None,
             vence_en=3600, emisor="https://accounts.google.com", clave=CLAVE_GOOGLE):
    ahora = int(time.time())
    claims = {"iss": emisor, "aud": aud, "sub": sub, "email": email, "email_verified": verificado,
              "nonce": nonce, "iat": ahora, "exp": ahora + vence_en}
    if hd:
        claims["hd"] = hd
    return jwt.encode(claims, clave, algorithm="RS256", headers={"kid": "prueba"})
