import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Secrets
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    # SQLite database file stored inside backend/ as futsalslot.db
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "futsalslot.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session cookie name for our auth token
    AUTH_COOKIE_NAME = "futsalslot_session"

    # 8 hours session lifetime 
    SESSION_LIFETIME_SECONDS = 8 * 60 * 60

    # Idle timeout: 20 minutes 
    IDLE_TIMEOUT_SECONDS = 20 * 60

    # Session/cookie security defaults 
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # set True when using HTTPS

    # Brute-force protection
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES = 1

    # Basic app settings
    DEBUG = False
