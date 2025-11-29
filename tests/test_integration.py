"""Integration tests for fasthook - increases code coverage."""

import pytest
import asyncio
import json
import time
from pathlib import Path
from io import StringIO
from unittest.mock import patch, AsyncMock, Mock

from fasthook.cli import listen, replay, mock, main
from fasthook.logger import Logger, Forwarder, EventCoordinator, EventLogger
from fasthook.replay import EventReplayer
from fasthook.mock import MockServer
from fasthook.server import create_app
from fasthook.utils import get_timestamp, safe_parse_json, safe_decode_body, pretty_print

from click.testing import CliRunner
from fastapi.testclient import TestClient


@pytest.fixture
def integration_events_file(tmp_path):
    """Create a sample events file for integration tests."""
    file_path = tmp_path / "integration_events.json"
    events = [
        {
            "timestamp": "2024-01-01T12:00:00.000Z",
            "method": "POST",
            "path": "/webhook/test",
            "headers": {"content-type": "application/json"},
            "query": {"source": "test"},
            "json": {"event": "test_event", "data": {"value": 123}},
            "raw": "",
            "ip": "192.168.1.100"
        },
        {
            "timestamp": "2024-01-01T12:00:01.000Z",
            "method": "GET",
            "path": "/status",
            "headers": {},
            "query": {},
            "json": None,
            "raw": "status check",
            "ip": "192.168.1.101"
        }
    ]
    with open(file_path, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')
    return file_path


class TestLoggerIntegration:
    """Integration tests for Logger functionality."""
    
    @pytest.mark.asyncio
    async def test_logger_with_file_and_console(self, tmp_path, capsys):
        """Test logger writing to both file and console."""
        file_path = tmp_path / "test_events.json"
        logger = Logger(save_path=file_path, quiet=False, pretty=True)
        
        event = {
            "timestamp": get_timestamp(),
            "method": "POST",
            "path": "/test",
            "headers": {"x-test": "value"},
            "query": {"q": "search"},
            "json": {"key": "value"},
            "raw": "",
            "ip": "127.0.0.1"
        }
        
        await logger.log_event(event)
        
        # Check file output
        assert file_path.exists()
        content = json.loads(file_path.read_text())
        assert content["method"] == "POST"
        assert content["json"]["key"] == "value"
        
        # Check console output
        captured = capsys.readouterr()
        assert "POST /test" in captured.out
        assert "x-test" in captured.out
    
    @pytest.mark.asyncio
    async def test_logger_with_binary_io(self):
        """Test logger with binary IO object."""
        from io import BytesIO
        buffer = BytesIO()
        buffer.mode = 'wb'
        
        logger = Logger(save_path=buffer, quiet=True)
        
        event = {
            "timestamp": get_timestamp(),
            "method": "GET",
            "path": "/api",
            "headers": {},
            "query": {},
            "json": {"test": "data"},
            "raw": "",
            "ip": "127.0.0.1"
        }
        
        await logger.log_event(event)
        
        buffer.seek(0)
        content = json.loads(buffer.read().decode('utf-8'))
        assert content["json"]["test"] == "data"


class TestForwarderIntegration:
    """Integration tests for Forwarder functionality."""
    
    @pytest.mark.asyncio
    async def test_forwarder_end_to_end(self):
        """Test forwarder with actual async operations."""
        forwarder = Forwarder(
            forward_url="http://example.com/webhook",
            forward_retries=2,
            forward_concurrency=3,
            quiet=True
        )
        
        event = {
            "timestamp": get_timestamp(),
            "method": "POST",
            "path": "/webhook",
            "headers": {"content-type": "application/json"},
            "query": {},
            "json": {"test": "data"},
            "raw": "",
            "ip": "127.0.0.1"
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_client.return_value = mock_instance
            
            await forwarder.start()
            forwarder._http_client = mock_instance
            
            await forwarder.forward_event(event)
            
            # Give worker time to process
            await asyncio.sleep(0.1)
            
            await forwarder.stop()
            
            # Verify request was made
            assert mock_instance.request.called


class TestEventCoordinatorIntegration:
    """Integration tests for EventCoordinator."""
    
    @pytest.mark.asyncio
    async def test_coordinator_full_workflow(self, tmp_path):
        """Test coordinator with logger and forwarder together."""
        file_path = tmp_path / "events.json"
        logger = Logger(save_path=file_path, quiet=True)
        forwarder = Forwarder(forward_url="http://example.com", quiet=True)
        coordinator = EventCoordinator(logger, forwarder)
        
        event = {
            "timestamp": get_timestamp(),
            "method": "POST",
            "path": "/webhook",
            "headers": {},
            "query": {},
            "json": {"event": "test"},
            "raw": "",
            "ip": "127.0.0.1"
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_client.return_value = mock_instance
            
            await coordinator.start()
            forwarder._http_client = mock_instance
            
            await coordinator.handle_event(event)
            
            await asyncio.sleep(0.1)
            await coordinator.stop()
            
            # Verify logging
            assert file_path.exists()
            content = json.loads(file_path.read_text())
            assert content["json"]["event"] == "test"


class TestServerIntegration:
    """Integration tests for FastAPI server."""
    
    def test_server_captures_all_event_data(self, tmp_path):
        """Test that server captures all parts of a request."""
        file_path = tmp_path / "events.json"
        logger = EventLogger(save_path=file_path, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        # Send complex request
        response = client.post(
            "/api/v2/webhooks/github?source=integration&test=true",
            json={
                "repository": "test-repo",
                "action": "push",
                "commits": [{"id": "abc123", "message": "Test commit"}]
            },
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature": "sha256=test",
                "User-Agent": "GitHub-Hookshot/test"
            }
        )
        
        assert response.status_code == 200
        
        # Verify captured data
        event = json.loads(file_path.read_text())
        assert event["method"] == "POST"
        assert event["path"] == "/api/v2/webhooks/github"
        assert event["query"]["source"] == "integration"
        assert event["query"]["test"] == "true"
        assert "x-github-event" in event["headers"]
        assert event["json"]["repository"] == "test-repo"
        assert len(event["json"]["commits"]) == 1


class TestReplayerIntegration:
    """Integration tests for EventReplayer."""
    
    @pytest.mark.asyncio
    async def test_replayer_with_target(self, integration_events_file):
        """Test replayer sending to actual target."""
        replayer = EventReplayer(
            events_file=integration_events_file,
            target_url="http://localhost:3000",
            fixed_delay=0.01
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_instance.aclose = AsyncMock()
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            await replayer.replay()
            
            # Should have made 2 requests (2 events)
            assert mock_instance.request.call_count == 2
            
            # Verify first call
            first_call = mock_instance.request.call_args_list[0]
            assert first_call[1]['method'] == 'POST'
            assert 'webhook/test' in first_call[1]['url']
    
    @pytest.mark.asyncio
    async def test_replayer_timing_modes(self, integration_events_file):
        """Test different replay timing modes."""
        # Test with rate multiplier
        replayer = EventReplayer(
            events_file=integration_events_file,
            replay_once=True,
            rate=100.0  # Very fast
        )
        
        start = time.time()
        await replayer.replay()
        duration = time.time() - start
        
        # Should be very fast with 100x rate
        assert duration < 0.5


class TestMockServerIntegration:
    """Integration tests for MockServer."""
    
    def test_mock_server_sequence_behavior(self):
        """Test mock server with sequence responses."""
        spec = {
            "routes": {
                "/api/counter": {
                    "POST": {
                        "sequence": [
                            {"status": 200, "body": {"count": 1, "message": "First"}},
                            {"status": 200, "body": {"count": 2, "message": "Second"}},
                            {"status": 200, "body": {"count": 3, "message": "Third"}}
                        ]
                    }
                }
            }
        }
        
        server = MockServer(spec)
        app = server.create_app()
        client = TestClient(app)
        
        # Make sequential requests
        r1 = client.post("/api/counter")
        assert r1.json()["count"] == 1
        assert r1.json()["message"] == "First"
        
        r2 = client.post("/api/counter")
        assert r2.json()["count"] == 2
        
        r3 = client.post("/api/counter")
        assert r3.json()["count"] == 3
        
        # Should stay at last
        r4 = client.post("/api/counter")
        assert r4.json()["count"] == 3
    
    def test_mock_server_wildcard_matching(self):
        """Test mock server wildcard route matching."""
        spec = {
            "routes": {
                "/api/v1/*": {
                    "GET": {
                        "status": 200,
                        "body": {"version": "v1", "matched": "wildcard"}
                    }
                },
                "/api/v1/users": {
                    "GET": {
                        "status": 200,
                        "body": {"version": "v1", "matched": "exact"}
                    }
                }
            }
        }
        
        server = MockServer(spec)
        app = server.create_app()
        client = TestClient(app)
        
        # Exact match should win
        r1 = client.get("/api/v1/users")
        assert r1.json()["matched"] == "exact"
        
        # Wildcard should match others
        r2 = client.get("/api/v1/posts")
        assert r2.json()["matched"] == "wildcard"
        
        r3 = client.get("/api/v1/comments/123")
        assert r3.json()["matched"] == "wildcard"


class TestCLIIntegrationCommands:
    """Integration tests for CLI commands."""
    
    def test_cli_listen_creates_server(self, tmp_path):
        """Test that listen command creates server with correct config."""
        runner = CliRunner()
        save_path = tmp_path / "events.json"
        
        with patch('fasthook.cli.uvicorn.run') as mock_uvicorn:
            result = runner.invoke(listen, [
                '8080',
                '--save', str(save_path),
                '--forward', 'http://api.example.com/webhook',
                '--host', '0.0.0.0',
                '--pretty',
                '--forward-retries', '5'
            ])
            
            assert result.exit_code == 0
            mock_uvicorn.assert_called_once()
            
            # Verify configuration
            call_kwargs = mock_uvicorn.call_args[1]
            assert call_kwargs['port'] == 8080
            assert call_kwargs['host'] == '0.0.0.0'
    
    def test_cli_mock_loads_and_runs(self, tmp_path):
        """Test that mock command loads spec and creates server."""
        runner = CliRunner()
        spec_file = tmp_path / "mock_spec.json"
        spec_file.write_text(json.dumps({
            "defaults": {"status": 200},
            "routes": {
                "/test": {
                    "GET": {"body": {"result": "ok"}}
                }
            }
        }))
        
        with patch('fasthook.cli.uvicorn.run') as mock_uvicorn:
            result = runner.invoke(mock, [
                '9000',
                '--spec', str(spec_file),
                '--host', '0.0.0.0'
            ])
            
            assert result.exit_code == 0
            assert 'Mock server running' in result.output
            mock_uvicorn.assert_called_once()


class TestUtilsIntegration:
    """Integration tests for utility functions."""
    
    def test_utils_with_real_data(self):
        """Test utils with realistic data."""
        # Test timestamp
        ts1 = get_timestamp()
        time.sleep(0.01)
        ts2 = get_timestamp()
        assert ts1 < ts2
        assert 'T' in ts1
        assert ts1.endswith('Z')
        
        # Test JSON parsing with complex data
        complex_data = {
            "nested": {
                "array": [1, 2, 3],
                "object": {"key": "value"}
            },
            "unicode": "Hello 世界 🚀"
        }
        json_bytes = json.dumps(complex_data).encode('utf-8')
        parsed = safe_parse_json(json_bytes)
        assert parsed == complex_data
        
        # Test binary decoding
        binary_data = b"\xff\xfe\xfd\xfc\xfb"
        decoded = safe_decode_body(binary_data)
        assert isinstance(decoded, str)
        # Should be base64 encoded
        import base64
        assert decoded == base64.b64encode(binary_data).decode('ascii')
    
    def test_pretty_print_various_types(self, capsys):
        """Test pretty print with various data types."""
        # Dict
        pretty_print({"key": "value", "number": 42})
        captured = capsys.readouterr()
        assert "key" in captured.out
        
        # List
        pretty_print([1, 2, 3, "test"])
        captured = capsys.readouterr()
        assert "test" in captured.out
        
        # With pprint
        pretty_print({"nested": {"data": "value"}}, use_pprint=True)
        captured = capsys.readouterr()
        assert "nested" in captured.out


class TestEventLoggerLegacy:
    """Integration tests for legacy EventLogger interface."""
    
    @pytest.mark.asyncio
    async def test_legacy_event_logger_workflow(self, tmp_path):
        """Test legacy EventLogger with full workflow."""
        file_path = tmp_path / "legacy_events.json"
        event_logger = EventLogger(
            save_path=file_path,
            forward_url="http://example.com/webhook",
            pretty=True,
            quiet=True
        )
        
        events = [
            {
                "timestamp": get_timestamp(),
                "method": "POST",
                "path": "/webhook",
                "headers": {},
                "query": {},
                "json": {"event": "test1"},
                "raw": "",
                "ip": "127.0.0.1"
            },
            {
                "timestamp": get_timestamp(),
                "method": "GET",
                "path": "/status",
                "headers": {},
                "query": {},
                "json": None,
                "raw": "ok",
                "ip": "127.0.0.1"
            }
        ]
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_client.return_value = mock_instance
            
            event_logger.forwarder._http_client = mock_instance
            
            for event in events:
                await event_logger.log(event)
            
            await asyncio.sleep(0.1)
            await event_logger.close()
        
        # Verify events were saved
        assert file_path.exists()
        lines = file_path.read_text().strip().split('\n')
        assert len(lines) == 2


class TestEndToEndScenarios:
    """End-to-end integration tests."""
    
    def test_receive_and_forward_workflow(self, tmp_path):
        """Test receiving webhook and forwarding it."""
        file_path = tmp_path / "e2e_events.json"
        logger = EventLogger(
            save_path=file_path,
            forward_url="http://downstream.example.com/webhook",
            quiet=True
        )
        
        app = create_app(logger)
        client = TestClient(app)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_client.return_value = mock_instance
            
            logger.forwarder._http_client = mock_instance
            
            # Send webhook
            response = client.post(
                "/webhooks/payment",
                json={
                    "event": "payment.success",
                    "amount": 100.00,
                    "currency": "USD"
                }
            )
            
            assert response.status_code == 200
            
            # Give time for async forwarding
            time.sleep(0.2)
        
        # Verify event was logged
        assert file_path.exists()
        event = json.loads(file_path.read_text())
        assert event["json"]["event"] == "payment.success"
        assert event["json"]["amount"] == 100.00
    
    @pytest.mark.asyncio
    async def test_record_and_replay_scenario(self, tmp_path):
        """Test recording events and replaying them."""
        # Step 1: Record events
        record_file = tmp_path / "recorded.json"
        logger = EventLogger(save_path=record_file, quiet=True)
        app = create_app(logger)
        client = TestClient(app)
        
        # Send some webhooks
        client.post("/webhook/1", json={"event": "first"})
        client.post("/webhook/2", json={"event": "second"})
        client.get("/status")
        
        # Step 2: Replay events
        replayer = EventReplayer(
            events_file=record_file,
            target_url="http://replay-target.com",
            fixed_delay=0.01
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_instance.aclose = AsyncMock()
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            await replayer.replay()
            
            # Should have replayed 3 events
            assert mock_instance.request.call_count == 3