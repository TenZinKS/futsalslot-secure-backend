from flask import Flask
from config import Config
from routes import health_bp, auth_bp

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

    return app

if __name__ == "__main__":
    app = create_app()
    # Run locally
    app.run(host="127.0.0.1", port=5002)
