from datetime import datetime, timedelta
from flask import request, current_app

from models import db
from models.login_attempt import LoginAttempt

def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

def is_locked(email: str) -> tuple[bool, int]:
    """
    Returns (locked, seconds_remaining)
    """
    ip = _client_ip()
    row = LoginAttempt.query.filter_by(email=email, ip=ip).first()
    if not row or not row.locked_until:
        return False, 0

    now = datetime.utcnow()
    if row.locked_until <= now:
        return False, 0

    seconds = int((row.locked_until - now).total_seconds())
    return True, max(seconds, 1)

def register_failure(email: str) -> tuple[int, bool]:
    """
    Increments failure counter. Returns (fail_count, locked_now)
    """
    ip = _client_ip()
    now = datetime.utcnow()

    row = LoginAttempt.query.filter_by(email=email, ip=ip).first()
    if not row:
        row = LoginAttempt(email=email, ip=ip, fail_count=0)
        db.session.add(row)

    row.fail_count += 1
    row.last_fail_at = now

    max_attempts = current_app.config.get("MAX_LOGIN_ATTEMPTS", 5)
    lock_minutes = current_app.config.get("LOCKOUT_MINUTES", 10)

    locked_now = False
    if row.fail_count >= max_attempts:
        row.locked_until = now + timedelta(minutes=lock_minutes)
        locked_now = True

    db.session.commit()
    return row.fail_count, locked_now

def reset_attempts(email: str):
    """
    Clears failure counter after successful login.
    """
    ip = _client_ip()
    row = LoginAttempt.query.filter_by(email=email, ip=ip).first()
    if not row:
        return
    row.fail_count = 0
    row.last_fail_at = None
    row.locked_until = None
    db.session.commit()
