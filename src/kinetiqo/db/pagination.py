import base64
import json
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger("kinetiqo")


def encode_cursor(sort_val: Any, start_date: str, activity_id: int) -> str:
    """Encodes pagination tie-breaker values into an opaque URL-safe base64 cursor."""
    payload = {
        "v": sort_val,
        "d": str(start_date),
        "id": int(activity_id),
    }
    dumped = json.dumps(payload, separators=(',', ':'))
    return base64.urlsafe_b64encode(dumped.encode('utf-8')).decode('ascii')


def decode_cursor(cursor_str: Optional[str]) -> Optional[Tuple[Any, str, int]]:
    """Decodes an opaque URL-safe base64 cursor.
    
    Returns:
        (sort_val, start_date, activity_id) or None if cursor is missing or invalid.
    """
    if not cursor_str:
        return None
    try:
        raw_json = base64.urlsafe_b64decode(cursor_str.encode('ascii')).decode('utf-8')
        payload = json.loads(raw_json)
        return payload.get("v"), str(payload.get("d")), int(payload.get("id"))
    except Exception as e:
        logger.warning("Failed to decode cursor %r: %s", cursor_str, e)
        return None
