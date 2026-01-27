import re
from typing import List, Tuple

try:
    from flask import current_app
except Exception:  # pragma: no cover - used outside app context (tests/CLI)
    current_app = None

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")
_SYMBOL = re.compile(r"[^A-Za-z0-9]")

_DEFAULTS = {
    "PASSWORD_MIN_LEN": 12,
    "PASSWORD_MAX_LEN": 128,
    "PASSWORD_REQUIRE_UPPER": True,
    "PASSWORD_REQUIRE_LOWER": True,
    "PASSWORD_REQUIRE_DIGIT": True,
    "PASSWORD_REQUIRE_SYMBOL": True,
}


def _cfg(name: str):
    if current_app is None:
        return _DEFAULTS[name]
    try:
        return current_app.config.get(name, _DEFAULTS[name])
    except RuntimeError:
        return _DEFAULTS[name]

def validate_password(pw: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if not isinstance(pw, str):
        return False, ["Password must be a string"]

    min_len = int(_cfg("PASSWORD_MIN_LEN"))
    max_len = int(_cfg("PASSWORD_MAX_LEN"))
    require_upper = bool(_cfg("PASSWORD_REQUIRE_UPPER"))
    require_lower = bool(_cfg("PASSWORD_REQUIRE_LOWER"))
    require_digit = bool(_cfg("PASSWORD_REQUIRE_DIGIT"))
    require_symbol = bool(_cfg("PASSWORD_REQUIRE_SYMBOL"))

    if len(pw) < min_len:
        errors.append(f"Password must be at least {min_len} characters")
    if len(pw) > max_len:
        errors.append(f"Password must be at most {max_len} characters")

    if require_upper and not _UPPER.search(pw):
        errors.append("Password must include at least 1 uppercase letter")
    if require_lower and not _LOWER.search(pw):
        errors.append("Password must include at least 1 lowercase letter")
    if require_digit and not _DIGIT.search(pw):
        errors.append("Password must include at least 1 number")
    if require_symbol and not _SYMBOL.search(pw):
        errors.append("Password must include at least 1 symbol")

    return (len(errors) == 0), errors


def password_strength(pw: str) -> dict:
    if not isinstance(pw, str):
        return {
            "score": 0,
            "valid": False,
            "feedback": ["Password must be a string"],
        }

    valid, errors = validate_password(pw)
    length = len(pw)
    min_len = int(_cfg("PASSWORD_MIN_LEN"))
    require_upper = bool(_cfg("PASSWORD_REQUIRE_UPPER"))
    require_lower = bool(_cfg("PASSWORD_REQUIRE_LOWER"))
    require_digit = bool(_cfg("PASSWORD_REQUIRE_DIGIT"))
    require_symbol = bool(_cfg("PASSWORD_REQUIRE_SYMBOL"))

    checks = []
    if require_upper:
        checks.append(_UPPER)
    if require_lower:
        checks.append(_LOWER)
    if require_digit:
        checks.append(_DIGIT)
    if require_symbol:
        checks.append(_SYMBOL)

    variety = sum(1 for pat in checks if pat.search(pw)) if checks else 0
    max_variety = max(1, len(checks))

    score = 0
    if length >= min_len:
        score += 1
    if length >= min_len + 4:
        score += 1
    if variety >= min(3, max_variety):
        score += 1
    if variety == max_variety and length >= min_len:
        score += 1

    feedback: List[str] = []
    if not valid:
        feedback = errors
    else:
        if length < min_len + 4:
            feedback.append("Use a longer passphrase for extra strength")
        if variety < max_variety:
            feedback.append("Add more character variety to strengthen the password")

    return {
        "score": min(score, 4),
        "valid": valid,
        "feedback": feedback,
    }
