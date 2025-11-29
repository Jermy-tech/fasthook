"""Tests for utils module."""

import pytest
import json
import base64
from datetime import datetime, timezone
from io import StringIO
import sys

from fasthook.utils import (
    get_timestamp,
    safe_parse_json,
    safe_decode_body,
    pretty_print
)


class TestGetTimestamp:
    """Tests for get_timestamp function."""
    
    def test_returns_iso_format(self):
        """Test timestamp is in ISO 8601 format."""
        ts = get_timestamp()
        assert 'T' in ts
        assert ts.endswith('Z')
    
    def test_returns_utc_time(self):
        """Test timestamp is in UTC."""
        ts = get_timestamp()
        # Should be parseable as UTC
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        assert dt.tzinfo is not None
    
    def test_consecutive_calls_increase(self):
        """Test that consecutive calls produce increasing timestamps."""
        ts1 = get_timestamp()
        ts2 = get_timestamp()
        # Convert to datetime for comparison
        dt1 = datetime.fromisoformat(ts1.replace('Z', '+00:00'))
        dt2 = datetime.fromisoformat(ts2.replace('Z', '+00:00'))
        assert dt2 >= dt1


class TestSafeParseJson:
    """Tests for safe_parse_json function."""
    
    def test_parse_valid_json(self):
        """Test parsing valid JSON."""
        data = {"key": "value", "number": 42}
        body_bytes = json.dumps(data).encode('utf-8')
        result = safe_parse_json(body_bytes)
        assert result == data
    
    def test_parse_empty_bytes(self):
        """Test parsing empty bytes returns None."""
        result = safe_parse_json(b"")
        assert result is None
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns None."""
        body_bytes = b"not valid json {{"
        result = safe_parse_json(body_bytes)
        assert result is None
    
    def test_parse_non_utf8(self):
        """Test parsing non-UTF-8 bytes returns None."""
        body_bytes = b"\xff\xfe invalid utf-8"
        result = safe_parse_json(body_bytes)
        assert result is None
    
    def test_parse_array(self):
        """Test parsing JSON array."""
        data = [1, 2, 3, "test"]
        body_bytes = json.dumps(data).encode('utf-8')
        result = safe_parse_json(body_bytes)
        assert result == data
    
    def test_parse_nested_json(self):
        """Test parsing nested JSON structures."""
        data = {
            "nested": {
                "deep": {
                    "value": "test"
                }
            },
            "array": [1, 2, {"key": "val"}]
        }
        body_bytes = json.dumps(data).encode('utf-8')
        result = safe_parse_json(body_bytes)
        assert result == data


class TestSafeDecodeBody:
    """Tests for safe_decode_body function."""
    
    def test_decode_utf8(self):
        """Test decoding valid UTF-8."""
        text = "Hello, World! 你好"
        body_bytes = text.encode('utf-8')
        result = safe_decode_body(body_bytes)
        assert result == text
    
    def test_decode_empty_bytes(self):
        """Test decoding empty bytes returns empty string."""
        result = safe_decode_body(b"")
        assert result == ""
    
    def test_decode_binary_data(self):
        """Test decoding binary data returns base64."""
        body_bytes = b"\xff\xfe\xfd\xfc"
        result = safe_decode_body(body_bytes)
        # Should be base64 encoded
        assert result == base64.b64encode(body_bytes).decode('ascii')
    
    def test_decode_mixed_content(self):
        """Test decoding content with invalid UTF-8 sequences."""
        body_bytes = b"valid text \xff invalid"
        result = safe_decode_body(body_bytes)
        # Should return base64 since UTF-8 decode fails
        assert result == base64.b64encode(body_bytes).decode('ascii')
    
    def test_decode_plain_text(self):
        """Test decoding plain ASCII text."""
        text = "Simple ASCII text 123"
        body_bytes = text.encode('utf-8')
        result = safe_decode_body(body_bytes)
        assert result == text


class TestPrettyPrint:
    """Tests for pretty_print function."""
    
    def test_print_dict(self, capsys):
        """Test pretty printing a dictionary."""
        data = {"key": "value", "number": 42}
        pretty_print(data)
        captured = capsys.readouterr()
        assert "key" in captured.out
        assert "value" in captured.out
        assert "42" in captured.out
    
    def test_print_list(self, capsys):
        """Test pretty printing a list."""
        data = [1, 2, 3, "test"]
        pretty_print(data)
        captured = capsys.readouterr()
        assert "test" in captured.out
    
    def test_print_with_pprint(self, capsys):
        """Test pretty printing with pprint option."""
        data = {"key": "value"}
        pretty_print(data, use_pprint=True)
        captured = capsys.readouterr()
        assert "key" in captured.out
    
    def test_print_unicode(self, capsys):
        """Test pretty printing unicode characters."""
        data = {"message": "Hello 你好 🚀"}
        pretty_print(data)
        captured = capsys.readouterr()
        assert "你好" in captured.out
        assert "🚀" in captured.out
    
    def test_print_nested_structure(self, capsys):
        """Test pretty printing nested structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": "deep value"
                }
            }
        }
        pretty_print(data)
        captured = capsys.readouterr()
        assert "level1" in captured.out
        assert "level3" in captured.out
        assert "deep value" in captured.out
    
    def test_print_non_serializable_fallback(self, capsys):
        """Test printing non-JSON-serializable object falls back."""
        # Create object that can't be JSON serialized
        class CustomObj:
            pass
        
        obj = CustomObj()
        pretty_print(obj)
        captured = capsys.readouterr()
        # Should still print something (the object repr)
        assert "CustomObj" in captured.out