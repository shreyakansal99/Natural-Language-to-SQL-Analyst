"""Soft checks for good UX and logging. The HARD enforcement is the validator
and the database privileges, so nothing here is a security boundary."""
import re

MAX_QUESTION_CHARS = 500


class GuardrailRefusal(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule


_DESTRUCTIVE = re.compile(
    r"\b(drop|truncate)\s+(the\s+|all\s+)?(\w+\s+)?(table|database|schema)\b"
    r"|\bdelete\s+(all|every|from|the)\b"
    r"|\b(update|insert)\s+(into|all|every|the)\b"
    r"|\b(grant|revoke)\s+(me|access|all|privileges?)\b",
    re.I)

_CREDENTIALS = re.compile(
    r"\b(passwords?|credentials?|hash(es)?|ssn|social security|credit cards?)\b", re.I)

_LISTING = re.compile(r"\b(list|show|give|display|export|dump|reveal)\b", re.I)
_CONTACT = re.compile(
    r"\b(phones?( numbers?)?|home address(es)?|street address(es)?|"
    r"dates? of birth|dob|birthdays?|full names?|email addresses|emails)\b", re.I)

_INJECTION = re.compile(
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions?|rules?|prompts?)"
    r"|(reveal|show|print|repeat)\b.{0,25}\b(system prompt|your instructions)"
    r"|\byou are now\b|\bdeveloper mode\b|\bjailbreak\b",
    re.I)


def check_question(question: str) -> str:
    """Return the cleaned question or raise GuardrailRefusal."""
    if not isinstance(question, str) or not question.strip():
        raise GuardrailRefusal("empty", "Please type a question about the sales data.")
    q = " ".join(question.split())
    if len(q) > MAX_QUESTION_CHARS:
        raise GuardrailRefusal("length", f"Please keep questions under {MAX_QUESTION_CHARS} characters.")
    if _INJECTION.search(q):
        raise GuardrailRefusal("injection", "I can only answer questions about the sales data.")
    if _DESTRUCTIVE.search(q):
        raise GuardrailRefusal("destructive", "This assistant is read-only. It can't change or delete data.")
    if _CREDENTIALS.search(q):
        raise GuardrailRefusal("sensitive", "That information isn't available through this assistant.")
    if _LISTING.search(q) and _CONTACT.search(q):
        raise GuardrailRefusal("pii", "I can't list personal contact details. "
                                      "I can answer aggregate questions, like customers per city.")
    return q


# ---- output redaction (catches PII-shaped text in results and explanations)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")      # masked 'jo***@x.com' does not match
_PHONE = re.compile(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|\+\d{1,3}[\s.-]?\d[\d\s.-]{7,}\d")
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def redact_text(text: str) -> str:
    text = _EMAIL.sub("[email hidden]", text)
    text = _PHONE.sub("[phone hidden]", text)
    return _CARD.sub("[number hidden]", text)


def redact_value(value):
    return redact_text(value) if isinstance(value, str) else value