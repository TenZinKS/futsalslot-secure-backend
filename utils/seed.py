from models import db
from models.user import Role

DEFAULT_ROLES = ["PLAYER", "ADMIN", "SUPER_ADMIN"]

def seed_roles():
    existing = {r.name for r in Role.query.all()}
    for name in DEFAULT_ROLES:
        if name not in existing:
            db.session.add(Role(name=name))
    db.session.commit()
