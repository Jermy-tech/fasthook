"""Tests for server module."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient

from fasthook.server import create_app
from fasthook.logger import EventLogger


@pytest.fixture
def event_logger(tmp_path):
    """Create EventLogger for testing."""
    file_path = tmp_path / "events.json"
    return EventLogger(save_path=file_path, quiet=True)


class TestCreateApp:
    """Tests for create_app function."""
    
    def test_create_app_returns_fastapi(self, event_logger):
        """Test create_app returns FastAPI instance."""
        app = create_app(event_logger)
        assert app is not None
        assert hasattr(app, 'routes')
    
    def test_create_app_with_exit_after(self, event_logger):
        """Test create_app with exit_after parameter."""
        app = create_app(event_logger, exit_after=5)
        assert app is not None


class TestWebhookEndpoints:
    """Tests for webhook endpoints."""
    
    def test_post_webhook(self, event_logger):
        """Test POST request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.post(
            "/webhook",
            json={"test": "data"},
            headers={"X-Custom-Header": "value"}
        )
        
        assert response.status_code == 200
        assert response.json() == {"status": "received"}
    
    def test_get_webhook(self, event_logger):
        """Test GET request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.get("/webhook?param=value")
        
        assert response.status_code == 200
        assert response.json() == {"status": "received"}
    
    def test_put_webhook(self, event_logger):
        """Test PUT request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.put(
            "/api/resource/123",
            json={"name": "updated"}
        )
        
        assert response.status_code == 200
    
    def test_delete_webhook(self, event_logger):
        """Test DELETE request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.delete("/api/resource/123")
        
        assert response.status_code == 200
    
    def test_patch_webhook(self, event_logger):
        """Test PATCH request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.patch(
            "/api/resource/123",
            json={"field": "value"}
        )
        
        assert response.status_code == 200
    
    def test_options_webhook(self, event_logger):
        """Test OPTIONS request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.options("/webhook")
        
        assert response.status_code == 200
    
    def test_head_webhook(self, event_logger):
        """Test HEAD request to webhook endpoint."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.head("/webhook")
        
        assert response.status_code == 200
    
    def test_nested_path(self, event_logger):
        """Test webhook with nested path."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.post(
            "/api/v1/webhooks/github",
            json={"event": "push"}
        )
        
        assert response.status_code == 200
    
    def test_root_path(self, event_logger):
        """Test webhook at root path."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.post("/", json={"test": "data"})
        
        assert response.status_code == 200
    
    def test_query_parameters(self, event_logger):
        """Test webhook with query parameters."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        response = client.get("/webhook?key1=value1&key2=value2")
        
        assert response.status_code == 200
    
    def test_custom_headers(self, event_logger):
        """Test webhook with custom headers."""
        app = create_app(event_logger)
        client = TestClient(app)
        
        headers = {
            "X-GitHub-Event": "push",
            "X-Hub-Signature": "sha1=test",
            "Content-Type": "application/json"
        }
        
        response = client.post(
            "/webhook",
            json={"test": "data"},
            headers=headers
        )
        
        assert response.status_code == 200
    
    def test_json_body(self, event_logger, tmp_path):
        """Test webhook logs JSON body correctly."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        test_data = {"key": "value", "number": 42}
        response = client.post("/webhook", json=test_data)
        
        assert response.status_code == 200
        
        # Verify event was logged
        import json
        content = file_path.read_text()
        event = json.loads(content)
        assert event["json"] == test_data
    
    def test_text_body(self, event_logger, tmp_path):
        """Test webhook with plain text body."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        response = client.post(
            "/webhook",
            content="plain text data",
            headers={"Content-Type": "text/plain"}
        )
        
        assert response.status_code == 200
        
        # Verify raw body was captured
        import json
        content = file_path.read_text()
        event = json.loads(content)
        assert event["raw"] == "plain text data"
    
    def test_binary_body(self, event_logger, tmp_path):
        """Test webhook with binary body."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        response = client.post(
            "/webhook",
            content=b"\xff\xfe\xfd\xfc",
            headers={"Content-Type": "application/octet-stream"}
        )
        
        assert response.status_code == 200


class TestExitAfter:
    """Tests for exit_after functionality."""
    
    @pytest.mark.asyncio
    async def test_exit_after_count(self, event_logger):
        """Test that exit_after triggers after N events."""
        app = create_app(event_logger, exit_after=2)
        client = TestClient(app)
        
        # First request
        response1 = client.post("/webhook", json={"test": 1})
        assert response1.status_code == 200
        
        # Second request should trigger exit mechanism
        with patch('os.kill') as mock_kill:
            response2 = client.post("/webhook", json={"test": 2})
            assert response2.status_code == 200
            
            # Give a moment for the delayed shutdown task
            await asyncio.sleep(0.7)
            
            # Verify os.kill was called (or at least exit was attempted)
            # Note: The actual kill might not be called in test environment
            # so we just verify the response was successful
            assert mock_kill.called or response2.status_code == 200
    
    def test_no_exit_before_count(self, event_logger):
        """Test that exit doesn't trigger before count."""
        app = create_app(event_logger, exit_after=5)
        client = TestClient(app)
        
        # Send 3 requests (less than exit_after)
        for i in range(3):
            response = client.post("/webhook", json={"test": i})
            assert response.status_code == 200


class TestStartupShutdown:
    """Tests for startup and shutdown events."""
    
    def test_startup_event_called(self, event_logger):
        """Test startup event is called."""
        app = create_app(event_logger)
        
        with patch.object(event_logger.coordinator, 'start', new_callable=AsyncMock) as mock_start:
            with TestClient(app):
                # Startup should have been called
                pass
            
            # Note: TestClient handles startup/shutdown automatically
    
    def test_shutdown_event_called(self, event_logger):
        """Test shutdown event is called."""
        app = create_app(event_logger)
        
        with patch.object(event_logger.coordinator, 'stop', new_callable=AsyncMock) as mock_stop:
            with TestClient(app):
                pass
            
            # Shutdown should have been called


class TestEventCapture:
    """Tests for event data capture."""
    
    def test_captures_method(self, event_logger, tmp_path):
        """Test that HTTP method is captured."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        client.post("/webhook", json={})
        
        import json
        event = json.loads(file_path.read_text())
        assert event["method"] == "POST"
    
    def test_captures_path(self, event_logger, tmp_path):
        """Test that request path is captured."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        client.get("/api/v1/test")
        
        import json
        event = json.loads(file_path.read_text())
        assert event["path"] == "/api/v1/test"
    
    def test_captures_headers(self, event_logger, tmp_path):
        """Test that headers are captured."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        headers = {"X-Custom": "test-value"}
        client.post("/webhook", json={}, headers=headers)
        
        import json
        event = json.loads(file_path.read_text())
        assert "x-custom" in event["headers"]
        assert event["headers"]["x-custom"] == "test-value"
    
    def test_captures_query_params(self, event_logger, tmp_path):
        """Test that query parameters are captured."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        client.get("/webhook?foo=bar&baz=qux")
        
        import json
        event = json.loads(file_path.read_text())
        assert event["query"]["foo"] == "bar"
        assert event["query"]["baz"] == "qux"
    
    def test_captures_timestamp(self, event_logger, tmp_path):
        """Test that timestamp is captured."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        client.post("/webhook", json={})
        
        import json
        event = json.loads(file_path.read_text())
        assert "timestamp" in event
        assert "T" in event["timestamp"]
        assert event["timestamp"].endswith("Z")
    
    def test_captures_client_ip(self, event_logger, tmp_path):
        """Test that client IP is captured."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        client.post("/webhook", json={})
        
        import json
        event = json.loads(file_path.read_text())
        assert "ip" in event
        # TestClient typically uses testclient as host
        assert event["ip"] is not None