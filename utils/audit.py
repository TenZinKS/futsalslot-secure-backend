import json
from flask import request
from models import db
from models.audit_log import AuditLog

def log_event(action: str, user_id=None, entity=None, entity_id=None, metadata=None):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    user_agent = request.headers.get("User-Agent", "")

    row = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        ip=ip,
        user_agent=user_agent[:255] if user_agent else None,
        metadata_json=json.dumps(metadata) if metadata else None
    )
    db.session.add(row)
    db.session.commit()
