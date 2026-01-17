from flask import Flask
from config import Config
from routes import health_bp, auth_bp,admin_bp

from models import db
from flask_migrate import Migrate
from utils.seed import seed_roles
from utils.auth_context import load_current_user


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register routes
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)


    # Database init
    db.init_app(app)
    
    # Migrations
    Migrate(app, db)

    # Seed default roles at startup (safe & idempotent)
    with app.app_context():
        seed_roles()

    @app.before_request
    def _load_user():
        load_current_user()

    register_cli(app)


    return app

#-------------------------
import click
from models.user import User, Role
from models import db

def register_cli(app):
    @app.cli.command("make-admin")
    @click.argument("email")
    def make_admin(email):
        """Promote a user to ADMIN by email (bootstrap)."""
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            print("User not found")
            return

        admin_role = Role.query.filter_by(name="ADMIN").first()
        if not admin_role:
            admin_role = Role(name="ADMIN")
            db.session.add(admin_role)
            db.session.commit()

        if admin_role not in user.roles:
            user.roles.append(admin_role)
            db.session.commit()

        print(f"{user.email} promoted to ADMIN")

#-------------------------

if __name__ == "__main__":
    app = create_app()
    # Run locally
    app.run(host="127.0.0.1", port=5002)
