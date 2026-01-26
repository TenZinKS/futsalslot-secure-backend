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

    # Simple IP rate limit for login endpoint
    LOGIN_RATE_WINDOW_SECONDS = 60      # window size
    LOGIN_RATE_MAX_REQUESTS = 15        # max login requests per IP per window

    #Cancellation policy
    CANCEL_CUTOFF_HOURS = 12

    # Password policy
    PASSWORD_HISTORY_COUNT = 2          # block last 2 passwords
    PASSWORD_MAX_AGE_DAYS = 90          # password expires after 90 days
    PROFILE_REQUIRED_FIELDS = ["full_name", "phone_number"]  # required before booking

    # Admin signup (set in environment for production)
    ADMIN_SIGNUP_CODE = os.getenv("ADMIN_SIGNUP_CODE")

    # Admin dashboard URL (used in verification emails)
    ADMIN_DASHBOARD_URL = os.getenv("ADMIN_DASHBOARD_URL")

    # Email (SMTP)
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    # Email OTP (post-login)
    OTP_LENGTH = int(os.getenv("OTP_LENGTH", "6"))
    OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))  # 5 minutes
    OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

    # Basic app settings
    DEBUG = False
