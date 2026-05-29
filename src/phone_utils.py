"""Phone number validation and formatting."""
import re


def clean_phone(raw) -> str | None:
    """
    Extract 10-digit US number from any common format.
    Returns 10-digit string or None.
    """
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return None
    if digits[0] in ("0", "1"):   # invalid area code
        return None
    if digits[3] in ("0", "1"):   # invalid exchange
        return None
    return digits


def fmt_e164(d10: str) -> str:
    return f"+1{d10}"


def fmt_display(d10: str) -> str:
    return f"+1 ({d10[:3]}) {d10[3:6]}-{d10[6:]}"
