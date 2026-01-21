import re
from typing import List, Tuple

# Minimum length already used: 12
MIN_LEN = 12
MAX_LEN = 128

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")
_SYMBOL = re.compile(r"[^A-Za-z0-9]")

def validate_password(pw: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if not isinstance(pw, str):
        return False, ["Password must be a string"]

    if len(pw) < MIN_LEN:
        errors.append(f"Password must be at least {MIN_LEN} characters")
    if len(pw) > MAX_LEN:
        errors.append(f"Password must be at most {MAX_LEN} characters")

    if not _UPPER.search(pw):
        errors.append("Password must include at least 1 uppercase letter")
    if not _LOWER.search(pw):
        errors.append("Password must include at least 1 lowercase letter")
    if not _DIGIT.search(pw):
        errors.append("Password must include at least 1 number")
    if not _SYMBOL.search(pw):
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
    variety = sum(1 for pat in (_UPPER, _LOWER, _DIGIT, _SYMBOL) if pat.search(pw))

    score = 0
    if length >= MIN_LEN:
        score += 1
    if length >= MIN_LEN + 4:
        score += 1
    if variety >= 3:
        score += 1
    if variety == 4 and length >= MIN_LEN:
        score += 1

    feedback: List[str] = []
    if not valid:
        feedback = errors
    else:
        if length < MIN_LEN + 4:
            feedback.append("Use a longer passphrase for extra strength")
        if variety < 4:
            feedback.append("Add more character variety to strengthen the password")

    return {
        "score": min(score, 4),
        "valid": valid,
        "feedback": feedback,
    }
