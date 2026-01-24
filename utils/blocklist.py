from models.blocked_email import BlockedEmail


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def is_email_blocked(email: str) -> bool:
    if not email:
        return False
    return BlockedEmail.query.filter_by(email_normalized=normalize_email(email)).first() is not None
