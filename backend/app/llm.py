import json
import threading
import time

from mistralai.client import Mistral
from app.config import MISTRAL_API_KEY, MISTRAL_MODEL

_client = Mistral(api_key=MISTRAL_API_KEY)

MIN_INTERVAL = 1.5        # seconds between calls (free tiers are strict)
MAX_RETRIES = 5
_lock = threading.Lock()
_last_call = 0.0


def _throttle():
    global _last_call
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _complete(**kwargs):
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            return _client.chat.complete(model=MISTRAL_MODEL, **kwargs)
        except Exception as e:
            is_429 = getattr(e, "status_code", None) == 429 or "429" in str(e)
            if not is_429 or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt * 2)      # 2, 4, 8, 16 seconds


def generate_json(system_prompt: str, user_message: str) -> dict:
    """Ask Mistral for a JSON object. The result is untrusted."""
    resp = _complete(
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_message}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        return {"sql": None, "needs_clarification": True,
                "reason": "Model returned invalid JSON"}


def generate_text(system_prompt: str, user_message: str) -> str:
    resp = _complete(
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_message}],
        temperature=0.2,
    )
    return resp.choices[0].message.content