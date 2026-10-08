"""Who is calling (F-login).

AUTH_MODE=none (default): single-user local mode, everything belongs to one local farmer.
AUTH_MODE=supabase: the app signs in with a Supabase email magic link (free tier) and sends the
access token as `Authorization: Bearer <jwt>`. The token is verified here (HS256 with
SUPABASE_JWT_SECRET, or the project's public JWKS keys) and mapped to a Kshetra user.
"""
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request

from app.api.deps import db, local_user_id
from app.config import get_settings


@lru_cache(maxsize=1)
def _jwks_client(url: str):
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def verify_token(token: str) -> dict:
    s = get_settings()
    try:
        if s.supabase_jwt_secret:
            return jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        key = _jwks_client(s.supabase_url).get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Please sign in again.") from exc


def current_user(request: Request, conn=Depends(db)) -> dict:
    if get_settings().auth_mode != "supabase":
        return {"id": local_user_id(conn), "email": None, "mode": "local"}
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.")
    claims = verify_token(header.split(" ", 1)[1])
    row = conn.execute(
        """INSERT INTO users (auth_id, email, name, preferred_language) VALUES (%s, %s, %s, 'te')
           ON CONFLICT (auth_id) DO UPDATE SET email = EXCLUDED.email RETURNING id::text""",
        (claims["sub"], claims.get("email"), (claims.get("email") or "").split("@")[0] or None),
    ).fetchone()
    conn.commit()
    return {"id": row["id"], "email": claims.get("email"), "mode": "supabase"}
