"""Utility functions for fasthook."""

import json
import base64
from datetime import datetime, timezone
from typing import Optional, Any


def get_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format.
    
    Returns:
        ISO 8601 formatted timestamp string
    """
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def safe_parse_json(body_bytes: bytes) -> Optional[dict]:
    """Safely parse JSON from bytes.
    
    Args:
        body_bytes: Raw body bytes
        
    Returns:
        Parsed JSON object or None if parsing fails
    """
    if not body_bytes:
        return None
    
    try:
        return json.loads(body_bytes.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def safe_decode_body(body_bytes: bytes) -> str:
    """Safely decode body bytes to string.
    
    Args:
        body_bytes: Raw body bytes
        
    Returns:
        UTF-8 decoded string or base64 encoded string if UTF-8 fails
    """
    if not body_bytes:
        return ""
    
    try:
        return body_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return base64.b64encode(body_bytes).decode('ascii')


def pretty_print(obj: Any) -> None:
    """Pretty print a JSON-serializable object.
    
    Args:
        obj: Object to print
    """
    try:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error pretty printing: {e}")
        print(obj)
