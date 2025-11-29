"""Comprehensive tests for fasthook package."""

import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import tempfile
import httpx

from fasthook.server import create_app
from fasthook.logger import EventLogger
from fasthook.utils import (
    get_timestamp,
    safe_parse_json,
    safe_decode_body,
    pretty_print
)
from fasthook.cli import main

from fastapi.testclient import TestClient


# ============================================================================
# Utility Tests
# ============================================================================

class TestUtils:
    """Tests for utility functions."""
    
    def test_get_timestamp_format(self):
        """Test timestamp is in correct ISO 8601 format."""
        ts = get_timestamp()
        assert ts.endswith('Z')
        # Should be parseable as datetime
        datetime.fromisoformat(ts.replace('Z', '+00:00'))
    
    def test_safe_parse_json_valid(self):
        """Test parsing valid JSON."""
        data = {"key": "value", "number": 42}
        body_bytes = json.dumps(data).encode('utf-8')
        result = safe_parse_json(body_bytes)
        assert result == data
    
    def test_safe_parse_json_invalid(self):
        """Test parsing invalid JSON returns None."""
        body_bytes = b"not json"
        result = safe_parse_json(body_bytes)
        assert result is None
    
    def test_safe_parse_json_empty(self):
        """Test parsing empty bytes returns None."""
        result = safe_parse_json(b"")
        assert result is None
    
    def test_safe_decode_body_utf8(self):
        """Test decoding valid UTF-8."""
        text = "Hello, World! 🚀"
        body_bytes = text.encode('utf-8')
        result = safe_decode_body(body_bytes)
        assert result == text
    
    def test_safe_decode_body_binary(self):
        """Test decoding binary data returns base64."""
        body_bytes = b"\x80\x81\x82\x83"
        result = safe_decode_body(body_bytes)
        # Should be base64 encoded
        assert isinstance(result, str)
        # Should be decodable from base64
        import base64
        base64.b64decode(result)
    
    def test_safe_decode_body_empty(self):
        """Test decoding empty bytes."""
        result = safe_decode_body(b"")
        assert result == ""
    
    def test_pretty_print_dict(self, capsys):
        """Test pretty printing a dictionary."""
        obj = {"key": "value", "nested": {"a": 1}}
        pretty_print(obj)
        captured = capsys.readouterr()
        assert "key" in captured.out
        assert "value" in captured.out
    
    def test_pretty_print_error(self, capsys, monkeypatch):
        """Test pretty print handles errors gracefully."""
        # Create an object that can't be JSON serialized
        class NonSerializable:
            pass
        
        obj = NonSerializable()
        pretty_print(obj)
        captured = capsys.readouterr()
        # Should fall back to printing the object directly
        assert "NonSerializable" in captured.out


# ============================================================================
# EventLogger Tests
# ============================================================================

class TestEventLogger:
    """Tests for EventLogger class."""
    
    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            path = Path(f.name)
        yield path
        if path.exists():
            path.unlink()
    
    @pytest.fixture
    def sample_event(self):
        """Sample webhook event."""
        return {
            "timestamp": "2024-01-01T00:00:00Z",
            "method": "POST",
            "path": "/webhook",
            "headers": {"content-type": "application/json"},
            "query": {"param": "value"},
            "json": {"data": "test"},
            "raw": "",
            "ip": "127.0.0.1"
        }
    
    @pytest.mark.asyncio
    async def test_logger_initialization(self):
        """Test EventLogger initializes correctly."""
        logger = EventLogger(
            save_path="test.json",
            forward_url="http://example.com",
            pretty=True,
            quiet=False
        )
        assert logger.save_path == "test.json"
        assert logger.forward_url == "http://example.com"
        assert logger.pretty is True
        assert logger.quiet is False
    
    @pytest.mark.asyncio
    async def test_save_event(self, temp_file, sample_event):
        """Test saving event to file."""
        logger = EventLogger(save_path=str(temp_file))
        await logger.log(sample_event)
        
        # Read the file and verify
        with open(temp_file, 'r') as f:
            saved_event = json.loads(f.readline())
        
        assert saved_event == sample_event
    
    @pytest.mark.asyncio
    async def test_save_multiple_events(self, temp_file, sample_event):
        """Test saving multiple events (newline-delimited)."""
        logger = EventLogger(save_path=str(temp_file))
        
        await logger.log(sample_event)
        event2 = sample_event.copy()
        event2["method"] = "GET"
        await logger.log(event2)
        
        # Read all events
        with open(temp_file, 'r') as f:
            events = [json.loads(line) for line in f]
        
        assert len(events) == 2
        assert events[0]["method"] == "POST"
        assert events[1]["method"] == "GET"
    
    @pytest.mark.asyncio
    async def test_quiet_mode(self, capsys, sample_event):
        """Test quiet mode suppresses output."""
        logger = EventLogger(quiet=True)
        await logger.log(sample_event)
        
        captured = capsys.readouterr()
        assert captured.out == ""
    
    @pytest.mark.asyncio
    async def test_print_event(self, capsys, sample_event):
        """Test printing event to console."""
        logger = EventLogger(quiet=False)
        await logger.log(sample_event)
        
        captured = capsys.readouterr()
        assert "POST" in captured.out
        assert "/webhook" in captured.out
        assert "127.0.0.1" in captured.out
    
    @pytest.mark.asyncio
    async def test_forward_event(self, sample_event):
        """Test forwarding event to URL."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=True
            )
            await logger.log(sample_event)
            
            # Verify request was made
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args
            assert call_args[1]['method'] == 'POST'
            assert call_args[1]['url'] == "http://example.com/webhook"
    
    @pytest.mark.asyncio
    async def test_close_http_client(self):
        """Test closing HTTP client."""
        logger = EventLogger(forward_url="http://example.com")
        # Initialize the client
        await logger._get_http_client()
        
        with patch.object(logger._http_client, 'aclose', new_callable=AsyncMock) as mock_close:
            await logger.close()
            mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_without_http_client(self):
        """Test closing when HTTP client was never created."""
        logger = EventLogger()
        await logger.close()  # Should not raise error
        assert logger._http_client is None
    
    @pytest.mark.asyncio
    async def test_save_event_error_handling(self, capsys, sample_event):
        """Test error handling when saving event fails."""
        logger = EventLogger(save_path="/invalid/path/that/does/not/exist/events.json")
        await logger.log(sample_event)
        
        captured = capsys.readouterr()
        assert "Error saving event" in captured.out
    
    @pytest.mark.asyncio
    async def test_print_event_with_empty_headers_and_query(self, capsys):
        """Test printing event with empty headers and query params."""
        logger = EventLogger(quiet=False)
        
        event = {
            'timestamp': '2024-01-01T00:00:00Z',
            'method': 'GET',
            'path': '/test',
            'headers': {},
            'query': {},
            'json': None,
            'raw': '',
            'ip': '127.0.0.1'
        }
        
        await logger._print_event(event)
        
        captured = capsys.readouterr()
        assert 'GET' in captured.out
        assert '/test' in captured.out
        # Should not print empty headers or query sections
    
    @pytest.mark.asyncio
    async def test_print_event_with_pretty_mode(self, capsys, sample_event):
        """Test printing event with pretty mode enabled."""
        logger = EventLogger(quiet=False, pretty=True)
        await logger._print_event(sample_event)
        
        captured = capsys.readouterr()
        assert 'POST' in captured.out
        # In pretty mode, JSON should be indented
        assert '  ' in captured.out  # Check for indentation
    
    @pytest.mark.asyncio
    async def test_print_event_with_raw_body(self, capsys):
        """Test printing event with raw body instead of JSON."""
        logger = EventLogger(quiet=False)
        
        event = {
            'timestamp': '2024-01-01T00:00:00Z',
            'method': 'POST',
            'path': '/webhook',
            'headers': {'content-type': 'text/plain'},
            'query': {},
            'json': None,
            'raw': 'This is raw text data',
            'ip': '127.0.0.1'
        }
        
        await logger._print_event(event)
        
        captured = capsys.readouterr()
        assert 'Raw Body:' in captured.out
        assert 'This is raw text data' in captured.out
    
    @pytest.mark.asyncio
    async def test_forward_removes_host_header(self, sample_event):
        """Test that host header is removed when forwarding."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=True
            )
            
            # Add host header to event
            event = sample_event.copy()
            event['headers']['host'] = 'original-host.com'
            
            await logger.log(event)
            
            # Verify host header was removed
            call_kwargs = mock_client.request.call_args[1]
            assert 'host' not in call_kwargs['headers']
    
    @pytest.mark.asyncio
    async def test_forward_with_quiet_false(self, capsys, sample_event):
        """Test forwarding prints status when not in quiet mode."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 201
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=False
            )
            
            await logger.log(sample_event)
            
            captured = capsys.readouterr()
            assert 'Forwarded to http://example.com/webhook: 201' in captured.out
    
    @pytest.mark.asyncio  
    async def test_forward_event_with_empty_body(self, sample_event):
        """Test forwarding event with no JSON and no raw body."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=True
            )
            
            # Event with neither JSON nor raw body
            event = sample_event.copy()
            event['json'] = None
            event['raw'] = None
            
            await logger.log(event)
            
            # Verify request was made with None body
            call_kwargs = mock_client.request.call_args[1]
            assert call_kwargs['content'] is None
    
    @pytest.mark.asyncio
    async def test_print_event_with_long_raw_body(self, capsys):
        """Test printing event with very long raw body (gets truncated)."""
        logger = EventLogger(quiet=False)
        
        # Create a raw body longer than 500 characters
        long_body = "x" * 600
        
        event = {
            'timestamp': '2024-01-01T00:00:00Z',
            'method': 'POST',
            'path': '/webhook',
            'headers': {},
            'query': {},
            'json': None,
            'raw': long_body,
            'ip': '127.0.0.1'
        }
        
        await logger._print_event(event)
        
        captured = capsys.readouterr()
        assert 'Raw Body:' in captured.out
        # Should be truncated to 500 chars
        assert len(captured.out.split('Raw Body:')[1].strip()) < 600
    
    @pytest.mark.asyncio
    async def test_forward_event_error_handling(self, capsys, sample_event):
        """Test error handling when forwarding fails."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = Exception("Network error")
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=True
            )
            await logger.log(sample_event)
            
            captured = capsys.readouterr()
            assert "Error forwarding event" in captured.out
    
    @pytest.mark.asyncio
    async def test_forward_event_with_raw_body(self, sample_event):
        """Test forwarding event with raw body instead of JSON."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=True
            )
            
            # Event with raw body but no JSON
            event = sample_event.copy()
            event['json'] = None
            event['raw'] = "raw text data"
            
            await logger.log(event)
            
            # Verify request was made with raw body
            mock_client.request.assert_called_once()
            call_kwargs = mock_client.request.call_args[1]
            assert call_kwargs['content'] == "raw text data"


# ============================================================================
# Server Tests
# ============================================================================

class TestServer:
    """Tests for FastAPI server."""
    
    @pytest.fixture
    def logger(self):
        """Mock EventLogger."""
        logger = Mock(spec=EventLogger)
        logger.log = AsyncMock()
        return logger
    
    @pytest.fixture
    def client(self, logger):
        """Test client for FastAPI app."""
        app = create_app(logger)
        return TestClient(app)
    
    def test_get_request(self, client, logger):
        """Test handling GET request."""
        response = client.get("/test/path?param=value")
        
        assert response.status_code == 200
        assert response.json() == {"status": "received"}
        
        # Verify logger was called
        logger.log.assert_called_once()
        event = logger.log.call_args[0][0]
        assert event["method"] == "GET"
        assert event["path"] == "/test/path"
        assert event["query"]["param"] == "value"
    
    def test_post_json(self, client, logger):
        """Test handling POST request with JSON."""
        data = {"key": "value", "number": 42}
        response = client.post("/webhook", json=data)
        
        assert response.status_code == 200
        
        # Verify event was logged correctly
        event = logger.log.call_args[0][0]
        assert event["method"] == "POST"
        assert event["json"] == data
    
    def test_post_raw_body(self, client, logger):
        """Test handling POST with raw body."""
        raw_data = "plain text data"
        response = client.post(
            "/webhook",
            content=raw_data,
            headers={"content-type": "text/plain"}
        )
        
        assert response.status_code == 200
        
        event = logger.log.call_args[0][0]
        assert event["raw"] == raw_data
    
    def test_put_request(self, client, logger):
        """Test handling PUT request."""
        response = client.put("/resource", json={"update": "data"})
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["method"] == "PUT"
    
    def test_delete_request(self, client, logger):
        """Test handling DELETE request."""
        response = client.delete("/resource/123")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["method"] == "DELETE"
        assert "/resource/123" in event["path"]
    
    def test_patch_request(self, client, logger):
        """Test handling PATCH request."""
        response = client.patch("/resource", json={"field": "value"})
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["method"] == "PATCH"
    
    def test_options_request(self, client, logger):
        """Test handling OPTIONS request."""
        response = client.options("/webhook")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["method"] == "OPTIONS"
    
    def test_head_request(self, client, logger):
        """Test handling HEAD request."""
        response = client.head("/webhook")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["method"] == "HEAD"
    
    def test_nested_path(self, client, logger):
        """Test handling nested path."""
        response = client.get("/api/v1/users/123/profile")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["path"] == "/api/v1/users/123/profile"
    
    def test_custom_headers(self, client, logger):
        """Test capturing custom headers."""
        headers = {
            "X-Custom-Header": "custom-value",
            "Authorization": "Bearer token123"
        }
        response = client.get("/webhook", headers=headers)
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert "x-custom-header" in event["headers"]
        assert event["headers"]["x-custom-header"] == "custom-value"
    
    def test_empty_body(self, client, logger):
        """Test handling request with empty body."""
        response = client.post("/webhook")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["json"] is None
        assert event["raw"] == ""
    
    def test_root_path(self, client, logger):
        """Test handling root path."""
        response = client.get("/")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["path"] == "/"
    
    def test_query_parameters(self, client, logger):
        """Test capturing multiple query parameters."""
        response = client.get("/webhook?foo=bar&baz=qux&key=value")
        
        assert response.status_code == 200
        event = logger.log.call_args[0][0]
        assert event["query"]["foo"] == "bar"
        assert event["query"]["baz"] == "qux"
        assert event["query"]["key"] == "value"


# ============================================================================
# CLI Tests
# ============================================================================

class TestCLI:
    """Tests for command-line interface."""
    
    @pytest.fixture
    def runner(self):
        """Click CLI test runner."""
        from click.testing import CliRunner
        return CliRunner()
    
    def test_main_group(self, runner):
        """Test main CLI group."""
        result = runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'fasthook' in result.output
    
    def test_listen_help(self, runner):
        """Test listen command help."""
        result = runner.invoke(main, ['listen', '--help'])
        assert result.exit_code == 0
        assert 'PORT' in result.output
        assert '--save' in result.output
        assert '--forward' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_basic(self, mock_uvicorn, runner):
        """Test basic listen command."""
        result = runner.invoke(main, ['listen', '3000'])
        
        assert result.exit_code == 0
        mock_uvicorn.assert_called_once()
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['port'] == 3000
        assert call_kwargs['host'] == '127.0.0.1'
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_save(self, mock_uvicorn, runner):
        """Test listen with save option."""
        result = runner.invoke(main, ['listen', '3000', '--save', 'events.json'])
        
        assert result.exit_code == 0
        assert 'events.json' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_forward(self, mock_uvicorn, runner):
        """Test listen with forward option."""
        result = runner.invoke(main, [
            'listen', '3000',
            '--forward', 'http://example.com/webhook'
        ])
        
        assert result.exit_code == 0
        assert 'http://example.com/webhook' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_quiet_mode(self, mock_uvicorn, runner):
        """Test listen in quiet mode."""
        result = runner.invoke(main, ['listen', '3000', '--quiet'])
        
        assert result.exit_code == 0
        # Should have minimal output
        assert 'fasthook listening' not in result.output
        
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['log_level'] == 'error'
        assert call_kwargs['access_log'] is False
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_custom_host(self, mock_uvicorn, runner):
        """Test listen with custom host."""
        result = runner.invoke(main, ['listen', '3000', '--host', '0.0.0.0'])
        
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['host'] == '0.0.0.0'
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_all_options(self, mock_uvicorn, runner):
        """Test listen with all options combined."""
        result = runner.invoke(main, [
            'listen', '3000',
            '--save', 'events.json',
            '--forward', 'http://example.com',
            '--pretty',
            '--host', '0.0.0.0'
        ])
        
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_debug_mode(self, mock_uvicorn, runner):
        """Test listen with debug flag."""
        result = runner.invoke(main, ['listen', '3000', '--debug'])
        
        assert result.exit_code == 0
        # Debug flag is passed through but doesn't affect much in current implementation
    
    def test_cli_listen_without_port(self, runner):
        """Test listen command without required PORT argument."""
        result = runner.invoke(main, ['listen'])
        
        assert result.exit_code != 0
        assert 'Missing argument' in result.output or 'PORT' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_all_flags_combined(self, mock_uvicorn, runner):
        """Test listen with every possible flag enabled."""
        result = runner.invoke(main, [
            'listen', '8080',
            '--save', 'test.json',
            '--forward', 'http://test.com',
            '--pretty',
            '--quiet',
            '--host', '0.0.0.0',
            '--debug'
        ])
        
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['port'] == 8080
        assert call_kwargs['host'] == '0.0.0.0'
        assert call_kwargs['log_level'] == 'error'
        assert call_kwargs['access_log'] is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_with_file_save(self, tmp_path):
        """Test complete flow from request to file save."""
        save_path = tmp_path / "events.json"
        logger = EventLogger(save_path=str(save_path), quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        # Make a request
        test_data = {"user": "test", "action": "login"}
        response = client.post("/api/login", json=test_data)
        
        assert response.status_code == 200
        
        # Verify file was created and contains data
        assert save_path.exists()
        with open(save_path, 'r') as f:
            event = json.loads(f.readline())
        
        assert event["method"] == "POST"
        assert event["path"] == "/api/login"
        assert event["json"] == test_data
    
    @pytest.mark.asyncio
    async def test_end_to_end_with_forward(self):
        """Test complete flow with request forwarding."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 201
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            logger = EventLogger(
                forward_url="http://example.com/webhook",
                quiet=True
            )
            app = create_app(logger)
            client = TestClient(app)
            
            # Make a request
            response = client.post("/webhook", json={"event": "test"})
            
            assert response.status_code == 200
            mock_client.request.assert_called_once()


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================================
# Test CLI main entry point
# ============================================================================

def test_cli_main_entry_point():
    """Test the CLI main entry point when run as script."""
    import subprocess
    import sys
    
    # Test that cli.py can be run as a module
    result = subprocess.run(
        [sys.executable, "-m", "fasthook.cli", "--help"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "fasthook" in result.stdout.lower()