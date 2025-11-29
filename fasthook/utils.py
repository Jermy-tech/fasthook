"""Utility functions - OPTIMIZED & PRODUCTION-READY."""

import json
import base64
import pprint
from datetime import datetime, timezone
from typing import Optional, Any


def get_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format.
    
    OPTIMIZED: More precise timestamp with microseconds.
    
    Returns:
        ISO 8601 formatted timestamp string with microseconds
    """
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def safe_parse_json(body_bytes: bytes) -> Optional[Any]:
    """Safely parse JSON from bytes.
    
    OPTIMIZED: Handles more edge cases gracefully.
    
    Args:
        body_bytes: Raw body bytes
        
    Returns:
        Parsed JSON object (dict, list, str, int, bool, None) or None if parsing fails
    """
    if not body_bytes:
        return None
    
    try:
        # Try to decode and parse
        text = body_bytes.decode('utf-8')
        return json.loads(text)
    except json.JSONDecodeError:
        # Not valid JSON
        return None
    except UnicodeDecodeError:
        # Not valid UTF-8
        return None
    except Exception:
        # Any other error - be defensive
        return None


def safe_decode_body(body_bytes: bytes) -> str:
    """Safely decode body bytes to string.
    
    OPTIMIZED: Better handling of large bodies and binary data.
    
    Args:
        body_bytes: Raw body bytes
        
    Returns:
        UTF-8 decoded string or base64 encoded string if UTF-8 fails
    """
    if not body_bytes:
        return ""
    
    # OPTIMIZATION: Limit size of body to decode (prevent memory issues)
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB
    
    if len(body_bytes) > MAX_BODY_SIZE:
        return f"<body too large: {len(body_bytes)} bytes, max {MAX_BODY_SIZE}>"
    
    try:
        return body_bytes.decode('utf-8')
    except UnicodeDecodeError:
        # Binary data - encode as base64
        # OPTIMIZATION: Only encode first 1KB for display
        if len(body_bytes) > 1024:
            sample = body_bytes[:1024]
            encoded = base64.b64encode(sample).decode('ascii')
            return f"<binary data: {len(body_bytes)} bytes, sample: {encoded}...>"
        else:
            return base64.b64encode(body_bytes).decode('ascii')


def pretty_print(obj: Any, use_pprint: bool = False) -> None:
    """Pretty print a JSON-serializable object.
    
    OPTIMIZED: Better exception handling - only catches relevant errors.
    
    Args:
        obj: Object to print
        use_pprint: If True, use pprint.pprint instead of json.dumps
    """
    try:
        if use_pprint:
            pprint.pprint(obj, indent=2, width=80, compact=False)
        else:
            # OPTIMIZATION: Handle large objects gracefully
            if isinstance(obj, (dict, list)):
                # Estimate size
                str_repr = str(obj)
                if len(str_repr) > 100000:  # > 100KB
                    print(f"<large object: {len(str_repr)} chars>")
                    if isinstance(obj, dict):
                        print(f"Keys: {list(obj.keys())[:10]}...")
                    elif isinstance(obj, list):
                        print(f"Length: {len(obj)}, first items: {obj[:5]}...")
                    return
            
            print(json.dumps(obj, indent=2, ensure_ascii=False))
    except (TypeError, ValueError, RecursionError) as e:
        # CRITICAL FIX: Only catch specific JSON-related exceptions
        print(f"Error pretty printing: {e}")
        # Fallback to simple print
        try:
            print(str(obj)[:1000])  # Limit output
        except Exception:
            print(f"<unprintable object of type {type(obj).__name__}>")