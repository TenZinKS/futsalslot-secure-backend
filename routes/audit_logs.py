from flask import Blueprint, jsonify, request
from models.audit_log import AuditLog
from security.rbac import require_roles

audit_bp = Blueprint("audit", __name__, url_prefix="/super-admin")


def _get_ts_attr():
    # Try common timestamp field names
    for name in ("created_at", "timestamp", "logged_at", "event_time", "time", "ts"):
        if hasattr(AuditLog, name):
            return name
    return None


@audit_bp.get("/audit-logs")
@require_roles("SUPER_ADMIN")
def list_audit_logs():
    
    limit = request.args.get("limit", type=int) or 200
    limit = max(1, min(limit, 500))

    action = request.args.get("action")
    user_id = request.args.get("user_id", type=int)

    q = AuditLog.query
    if action:
        q = q.filter(getattr(AuditLog, "action") == action)
    if user_id is not None and hasattr(AuditLog, "user_id"):
        q = q.filter(getattr(AuditLog, "user_id") == user_id)

    ts_attr = _get_ts_attr()
    if ts_attr:
        q = q.order_by(getattr(AuditLog, ts_attr).desc())
    else:
        # Always exists
        q = q.order_by(getattr(AuditLog, "id").desc())

    rows = q.limit(limit).all()
    column_names = set(AuditLog.__table__.columns.keys())

    out = []
    for r in rows:
        # timestamp value (optional)
        ts_val = getattr(r, ts_attr) if ts_attr else None
        ts_iso = ts_val.isoformat() if ts_val else None

        # metadata might be named metadata/json/meta
        meta_val = None
        for m in ("metadata", "meta", "data", "metadata_json"):
            if m in column_names:
                meta_val = getattr(r, m)
                break

        out.append({
            "id": getattr(r, "id", None),
            "created_at": ts_iso,
            "user_id": getattr(r, "user_id", None),
            "action": getattr(r, "action", None),
            "entity": getattr(r, "entity", None),
            "entity_id": getattr(r, "entity_id", None),
            "ip": getattr(r, "ip", None),
            "user_agent": getattr(r, "user_agent", None),
            "metadata": meta_val,
        })

    return jsonify(out), 200
