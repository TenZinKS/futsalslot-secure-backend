from flask import Blueprint, request, jsonify, g

from models import db
from models.support_message import SupportMessage
from models.court import Court
from utils.auth_context import login_required
from utils.audit import log_event

support_bp = Blueprint("support", __name__, url_prefix="/support")


@support_bp.post("/messages")
@login_required
def create_support_message():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    subject = (data.get("subject") or "").strip() or None
    court_id = data.get("court_id")

    if not message:
        return jsonify(error="message is required"), 400

    if court_id:
        court = Court.query.get(int(court_id))
        if not court:
            return jsonify(error="Court not found"), 404

    msg = SupportMessage(
        user_id=g.user.id,
        court_id=court_id,
        subject=subject,
        message=message,
        status="OPEN",
    )
    db.session.add(msg)
    db.session.commit()

    log_event("SUPPORT_MESSAGE_CREATE", user_id=g.user.id, entity="support_message", entity_id=msg.id)
    return jsonify(id=msg.id, status=msg.status), 201
