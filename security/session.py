import hashlib
import secrets
from datetime import datetime, timedelta
from flask import request, current_app

from models import db
from models.session import Session

def _hash_token(token: str) -> str:
    # SHA-256 is fine for hashing random session tokens
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_session(user_id: int) -> str:
    """
    Creates a server-side session and returns the RAW token (to set as cookie).
    Only the hash is stored in DB.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    lifetime = current_app.config.get("SESSION_LIFETIME_SECONDS", 28800)
    expires_at = datetime.utcnow() + timedelta(seconds=lifetime)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    user_agent = (request.headers.get("User-Agent") or "")[:255]

    row = Session(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        ip=ip,
        user_agent=user_agent,
    )
    db.session.add(row)
    db.session.commit()
    return raw_token

def get_session_from_request():
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "futsalslot_session")
    raw_token = request.cookies.get(cookie_name)
    if not raw_token:
        return None

    token_hash = _hash_token(raw_token)
    now = datetime.utcnow()

    sess = (
        Session.query
        .filter_by(token_hash=token_hash, revoked=False)
        .first()
    )
    if not sess:
        return None

    # Absolute expiry
    if sess.expires_at <= now:
        return None

    # Idle timeout
    idle_seconds = current_app.config.get("IDLE_TIMEOUT_SECONDS", 1200)
    last_seen = sess.last_seen_at or sess.created_at
    if (last_seen + timedelta(seconds=idle_seconds)) <= now:
        return None


    # Update activity timestamp (touch)
    sess.last_seen_at = now
    db.session.commit()

    return sess


def revoke_session(raw_token: str) -> bool:
    if not raw_token:
        return False
    token_hash = _hash_token(raw_token)
    sess = Session.query.filter_by(token_hash=token_hash).first()
    if not sess:
        return False
    sess.revoked = True
    db.session.commit()
    return True

def revoke_all_sessions(user_id: int) -> int:
    sessions = Session.query.filter_by(user_id=user_id, revoked=False).all()
    for s in sessions:
        s.revoked = True
    db.session.commit()
    return len(sessions)
