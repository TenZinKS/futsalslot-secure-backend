from datetime import datetime, timedelta
from flask import request, current_app

from models import db
from models.ip_rate_limit import IpRateLimit

def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

def check_and_increment_login_rate() -> tuple[bool, int]:
    """
    Returns (allowed, retry_after_seconds).
    Simple fixed window per IP.
    """
    ip = _client_ip()
    now = datetime.utcnow()

    window_seconds = current_app.config.get("LOGIN_RATE_WINDOW_SECONDS", 60)
    max_requests = current_app.config.get("LOGIN_RATE_MAX_REQUESTS", 15)

    row = IpRateLimit.query.filter_by(ip=ip).first()
    if not row:
        row = IpRateLimit(ip=ip, window_start=now, count=0)
        db.session.add(row)

    window_end = row.window_start + timedelta(seconds=window_seconds)

    # Reset window if expired
    if now >= window_end:
        row.window_start = now
        row.count = 0
        window_end = row.window_start + timedelta(seconds=window_seconds)

    row.count += 1
    db.session.commit()

    if row.count > max_requests:
        retry_after = int((window_end - now).total_seconds())
        return False, max(retry_after, 1)

    return True, 0
