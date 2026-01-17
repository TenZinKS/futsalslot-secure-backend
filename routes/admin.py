from flask import Blueprint, jsonify, g
from utils.auth_context import login_required
from security.rbac import require_roles
from utils.audit import log_event

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.get("/dashboard")
@require_roles("ADMIN", "STAFF")
def dashboard():
    log_event("ADMIN_DASHBOARD_VIEW", user_id=g.user.id)
    return jsonify(message="Welcome to staff/admin dashboard"), 200
