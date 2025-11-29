"""Tests for logger module."""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from io import StringIO, BytesIO
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from fasthook.logger import Logger, Forwarder, EventCoordinator, EventLogger


@pytest.fixture
def sample_event():
    """Sample webhook event for testing."""
    return {
        "timestamp": "2024-01-01T12:00:00Z",
        "method": "POST",
        "path": "/webhook",
        "headers": {"content-type": "application/json", "user-agent": "test"},
        "query": {"param": "value"},
        "json": {"test": "data"},
        "raw": "",
        "ip": "127.0.0.1"
    }


class TestLogger:
    """Tests for Logger class."""
    
    def test_init_default(self):
        """Test Logger initialization with defaults."""
        logger = Logger()
        assert logger.save_path is None
        assert logger.pretty is False
        assert logger.quiet is False
    
    def test_init_with_path(self, tmp_path):
        """Test Logger initialization with file path."""
        file_path = tmp_path / "events.json"
        logger = Logger(save_path=file_path)
        assert logger.save_path == file_path
    
    def test_init_with_string_path(self, tmp_path):
        """Test Logger initialization with string path."""
        file_path = str(tmp_path / "events.json")
        logger = Logger(save_path=file_path)
        assert isinstance(logger.save_path, Path)
    
    @pytest.mark.asyncio
    async def test_log_event_console_output(self, sample_event, capsys):
        """Test logging event to console."""
        logger = Logger(quiet=False)
        await logger.log_event(sample_event)
        
        captured = capsys.readouterr()
        assert "POST /webhook" in captured.out
        assert "127.0.0.1" in captured.out
        assert "test" in captured.out
    
    @pytest.mark.asyncio
    async def test_log_event_quiet_mode(self, sample_event, capsys):
        """Test logging event in quiet mode."""
        logger = Logger(quiet=True)
        await logger.log_event(sample_event)
        
        captured = capsys.readouterr()
        assert captured.out == ""
    
    @pytest.mark.asyncio
    async def test_save_event_to_file(self, sample_event, tmp_path):
        """Test saving event to file."""
        file_path = tmp_path / "events.json"
        logger = Logger(save_path=file_path, quiet=True)
        
        await logger.log_event(sample_event)
        
        assert file_path.exists()
        content = file_path.read_text()
        saved_event = json.loads(content)
        assert saved_event == sample_event
    
    @pytest.mark.asyncio
    async def test_save_multiple_events(self, sample_event, tmp_path):
        """Test saving multiple events (NDJSON format)."""
        file_path = tmp_path / "events.json"
        logger = Logger(save_path=file_path, quiet=True)
        
        await logger.log_event(sample_event)
        
        event2 = sample_event.copy()
        event2["method"] = "GET"
        await logger.log_event(event2)
        
        # Read as NDJSON
        lines = file_path.read_text().strip().split('\n')
        assert len(lines) == 2
        assert json.loads(lines[0])["method"] == "POST"
        assert json.loads(lines[1])["method"] == "GET"
    
    @pytest.mark.asyncio
    async def test_save_to_file_like_object(self, sample_event):
        """Test saving to file-like object."""
        buffer = StringIO()
        logger = Logger(save_path=buffer, quiet=True)
        
        await logger.log_event(sample_event)
        
        buffer.seek(0)
        content = buffer.read()
        saved_event = json.loads(content)
        assert saved_event == sample_event
    
    @pytest.mark.asyncio
    async def test_save_to_binary_file_like_object(self, sample_event):
        """Test saving to binary file-like object."""
        # BytesIO doesn't have a 'mode' attribute, so the logger code
        # will try to write as text, which will fail
        # This test verifies the actual behavior
        buffer = BytesIO()
        
        # Add a mode attribute to make it work like a binary file
        buffer.mode = 'wb'
        
        logger = Logger(save_path=buffer, quiet=True)
        
        await logger.log_event(sample_event)
        
        # Make sure data was written
        buffer.seek(0)
        raw_content = buffer.read()
        
        # Should have content
        assert len(raw_content) > 0
        
        # Decode and parse
        content = raw_content.decode('utf-8').strip()
        saved_event = json.loads(content)
        assert saved_event == sample_event
    
    @pytest.mark.asyncio
    async def test_pretty_print_json(self, sample_event, capsys):
        """Test pretty printing JSON body."""
        logger = Logger(pretty=True, quiet=False)
        await logger.log_event(sample_event)
        
        captured = capsys.readouterr()
        # Should have indentation
        assert '\n' in captured.out
        assert '"test"' in captured.out
    
    @pytest.mark.asyncio
    async def test_log_event_with_query_params(self, capsys):
        """Test logging event with query parameters."""
        event = {
            "timestamp": "2024-01-01T12:00:00Z",
            "method": "GET",
            "path": "/api",
            "headers": {},
            "query": {"key": "value", "filter": "active"},
            "json": None,
            "raw": "",
            "ip": "127.0.0.1"
        }
        logger = Logger(quiet=False)
        await logger.log_event(event)
        
        captured = capsys.readouterr()
        assert "Query:" in captured.out
    
    @pytest.mark.asyncio
    async def test_log_event_with_raw_body(self, capsys):
        """Test logging event with raw body."""
        event = {
            "timestamp": "2024-01-01T12:00:00Z",
            "method": "POST",
            "path": "/webhook",
            "headers": {},
            "query": {},
            "json": None,
            "raw": "raw body content here",
            "ip": "127.0.0.1"
        }
        logger = Logger(quiet=False)
        await logger.log_event(event)
        
        captured = capsys.readouterr()
        assert "Raw Body:" in captured.out
        assert "raw body content" in captured.out


class TestForwarder:
    """Tests for Forwarder class."""
    
    def test_init_default(self):
        """Test Forwarder initialization."""
        forwarder = Forwarder()
        assert forwarder.forward_url is None
        assert forwarder._forward_queue is None
    
    def test_init_with_url(self):
        """Test Forwarder initialization with URL."""
        forwarder = Forwarder(forward_url="http://example.com")
        assert forwarder.forward_url == "http://example.com"
        assert forwarder._forward_queue is not None
    
    @pytest.mark.asyncio
    async def test_start_creates_worker(self):
        """Test starting forwarder creates worker task."""
        forwarder = Forwarder(forward_url="http://example.com")
        await forwarder.start()
        
        assert forwarder._worker_task is not None
        assert not forwarder._worker_task.done()
        
        await forwarder.stop()
    
    @pytest.mark.asyncio
    async def test_stop_cancels_worker(self):
        """Test stopping forwarder cancels worker."""
        forwarder = Forwarder(forward_url="http://example.com")
        await forwarder.start()
        await forwarder.stop()
        
        assert forwarder._worker_task.cancelled() or forwarder._worker_task.done()
    
    @pytest.mark.asyncio
    async def test_forward_event_queues_event(self, sample_event):
        """Test forwarding event adds to queue."""
        forwarder = Forwarder(forward_url="http://example.com")
        
        await forwarder.forward_event(sample_event)
        
        assert forwarder._forward_queue.qsize() == 1
    
    @pytest.mark.asyncio
    async def test_forward_request_success(self, sample_event):
        """Test successful forward request."""
        forwarder = Forwarder(forward_url="http://example.com", quiet=True)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value = mock_instance
            
            forwarder._http_client = mock_instance
            
            await forwarder._forward_request(sample_event)
            
            mock_instance.request.assert_called_once()
            call_kwargs = mock_instance.request.call_args[1]
            assert call_kwargs['method'] == 'POST'
            assert call_kwargs['url'] == 'http://example.com'
    
    @pytest.mark.asyncio
    async def test_forward_with_retries(self, sample_event):
        """Test forward request with retries on failure."""
        forwarder = Forwarder(
            forward_url="http://example.com",
            forward_retries=3,
            quiet=True
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            # Fail twice, succeed on third attempt
            mock_instance.request.side_effect = [
                Exception("Network error"),
                Exception("Network error"),
                Mock(status_code=200)
            ]
            mock_client.return_value = mock_instance
            forwarder._http_client = mock_instance
            
            await forwarder._process_forward(sample_event)
            
            assert mock_instance.request.call_count == 3
    
    @pytest.mark.asyncio
    async def test_forward_concurrency_limit(self, sample_event):
        """Test forward concurrency limiting."""
        forwarder = Forwarder(
            forward_url="http://example.com",
            forward_concurrency=2,
            quiet=True
        )
        
        # Semaphore should limit to 2 concurrent
        assert forwarder._semaphore._value == 2


class TestEventCoordinator:
    """Tests for EventCoordinator class."""
    
    def test_init(self):
        """Test EventCoordinator initialization."""
        logger = Logger()
        forwarder = Forwarder(forward_url="http://example.com")
        coordinator = EventCoordinator(logger, forwarder)
        
        assert coordinator.logger is logger
        assert coordinator.forwarder is forwarder
    
    @pytest.mark.asyncio
    async def test_start_starts_forwarder(self):
        """Test starting coordinator starts forwarder."""
        logger = Logger()
        forwarder = Forwarder(forward_url="http://example.com")
        coordinator = EventCoordinator(logger, forwarder)
        
        await coordinator.start()
        
        assert forwarder._worker_task is not None
        
        await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_handle_event_logs_and_forwards(self, sample_event, tmp_path):
        """Test handling event logs and forwards."""
        file_path = tmp_path / "events.json"
        logger = Logger(save_path=file_path, quiet=True)
        forwarder = Forwarder(forward_url="http://example.com")
        coordinator = EventCoordinator(logger, forwarder)
        
        await coordinator.handle_event(sample_event)
        
        # Check logging worked
        assert file_path.exists()
        
        # Check forwarding queued
        assert forwarder._forward_queue.qsize() == 1


class TestEventLogger:
    """Tests for EventLogger (legacy compatibility)."""
    
    def test_init_legacy(self):
        """Test legacy EventLogger initialization."""
        event_logger = EventLogger(
            save_path=None,
            forward_url="http://example.com",
            pretty=True,
            quiet=False
        )
        
        assert event_logger.logger is not None
        assert event_logger.forwarder is not None
        assert event_logger.coordinator is not None
    
    @pytest.mark.asyncio
    async def test_log_legacy_interface(self, sample_event, tmp_path):
        """Test legacy log interface."""
        file_path = tmp_path / "events.json"
        event_logger = EventLogger(save_path=file_path, quiet=True)
        
        await event_logger.log(sample_event)
        
        assert file_path.exists()
        content = json.loads(file_path.read_text())
        assert content == sample_event
    
    @pytest.mark.asyncio
    async def test_close_legacy_interface(self):
        """Test legacy close interface."""
        event_logger = EventLogger(forward_url="http://example.com")
        await event_logger.coordinator.start()
        
        await event_logger.close()
        
        # Should not raise exception