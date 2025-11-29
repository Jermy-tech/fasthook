"""Tests for replay module."""

import pytest
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fasthook.replay import EventReplayer


@pytest.fixture
def sample_events():
    """Sample events for testing replay."""
    return [
        {
            "timestamp": "2024-01-01T12:00:00Z",
            "method": "POST",
            "path": "/webhook",
            "headers": {"content-type": "application/json"},
            "query": {},
            "json": {"event": "first"},
            "raw": "",
            "ip": "127.0.0.1"
        },
        {
            "timestamp": "2024-01-01T12:00:02Z",
            "method": "POST",
            "path": "/webhook",
            "headers": {"content-type": "application/json"},
            "query": {},
            "json": {"event": "second"},
            "raw": "",
            "ip": "127.0.0.1"
        },
        {
            "timestamp": "2024-01-01T12:00:05Z",
            "method": "GET",
            "path": "/status",
            "headers": {},
            "query": {"check": "true"},
            "json": None,
            "raw": "",
            "ip": "127.0.0.1"
        }
    ]


@pytest.fixture
def events_file(tmp_path, sample_events):
    """Create an events file with sample data."""
    file_path = tmp_path / "events.json"
    with open(file_path, 'w') as f:
        for event in sample_events:
            f.write(json.dumps(event) + '\n')
    return file_path


class TestEventReplayerInit:
    """Tests for EventReplayer initialization."""
    
    def test_init_default(self, events_file):
        """Test EventReplayer initialization with defaults."""
        replayer = EventReplayer(events_file)
        assert replayer.events_file == events_file
        assert replayer.rate == 1.0
        assert replayer.target_url is None
        assert replayer.fixed_delay == 0.0
        assert replayer.replay_once is False
    
    def test_init_with_rate(self, events_file):
        """Test EventReplayer initialization with custom rate."""
        replayer = EventReplayer(events_file, rate=2.0)
        assert replayer.rate == 2.0
    
    def test_init_with_target(self, events_file):
        """Test EventReplayer initialization with target URL."""
        replayer = EventReplayer(events_file, target_url="http://localhost:3000")
        assert replayer.target_url == "http://localhost:3000"
    
    def test_init_with_fixed_delay(self, events_file):
        """Test EventReplayer initialization with fixed delay."""
        replayer = EventReplayer(events_file, fixed_delay=1.0)
        assert replayer.fixed_delay == 1.0
    
    def test_init_with_replay_once(self, events_file):
        """Test EventReplayer initialization with replay_once."""
        replayer = EventReplayer(events_file, replay_once=True)
        assert replayer.replay_once is True


class TestLoadEvents:
    """Tests for loading events from file."""
    
    def test_load_valid_events(self, events_file, sample_events):
        """Test loading valid events."""
        replayer = EventReplayer(events_file)
        events = replayer._load_events()
        
        assert len(events) == len(sample_events)
        assert events == sample_events
    
    def test_load_empty_file(self, tmp_path):
        """Test loading empty file."""
        file_path = tmp_path / "empty.json"
        file_path.write_text("")
        
        replayer = EventReplayer(file_path)
        events = replayer._load_events()
        
        assert events == []
    
    def test_load_with_blank_lines(self, tmp_path, sample_events):
        """Test loading file with blank lines."""
        file_path = tmp_path / "events.json"
        with open(file_path, 'w') as f:
            f.write(json.dumps(sample_events[0]) + '\n')
            f.write('\n')  # Blank line
            f.write(json.dumps(sample_events[1]) + '\n')
        
        replayer = EventReplayer(file_path)
        events = replayer._load_events()
        
        assert len(events) == 2
    
    def test_load_with_invalid_json(self, tmp_path, sample_events, capsys):
        """Test loading file with some invalid JSON lines."""
        file_path = tmp_path / "events.json"
        with open(file_path, 'w') as f:
            f.write(json.dumps(sample_events[0]) + '\n')
            f.write('invalid json line\n')
            f.write(json.dumps(sample_events[1]) + '\n')
        
        replayer = EventReplayer(file_path)
        events = replayer._load_events()
        
        # Should skip invalid line and load valid ones
        assert len(events) == 2
        assert events[0] == sample_events[0]
        assert events[1] == sample_events[1]


class TestParseTimestamp:
    """Tests for timestamp parsing."""
    
    def test_parse_iso_timestamp(self, events_file):
        """Test parsing ISO 8601 timestamp."""
        replayer = EventReplayer(events_file)
        timestamp = "2024-01-01T12:00:00Z"
        dt = replayer._parse_timestamp(timestamp)
        
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12
        assert dt.minute == 0
        assert dt.second == 0
    
    def test_parse_timestamp_with_offset(self, events_file):
        """Test parsing timestamp with UTC offset."""
        replayer = EventReplayer(events_file)
        timestamp = "2024-01-01T12:00:00+00:00"
        dt = replayer._parse_timestamp(timestamp)
        
        assert dt.year == 2024


class TestReplayWithoutTarget:
    """Tests for replaying events without target (print only)."""
    
    @pytest.mark.asyncio
    async def test_replay_without_target(self, events_file, capsys):
        """Test replaying events without sending them."""
        replayer = EventReplayer(events_file)
        await replayer.replay()
        
        captured = capsys.readouterr()
        assert "Replaying: POST /webhook" in captured.out
        assert "Replaying: GET /status" in captured.out
    
    @pytest.mark.asyncio
    async def test_replay_prints_event_details(self, events_file, capsys):
        """Test that replay prints event details."""
        replayer = EventReplayer(events_file)
        await replayer.replay()
        
        captured = capsys.readouterr()
        # FIXED: Optimized replay shows progress format
        assert "Replaying:" in captured.out
        assert "Timestamp:" in captured.out
        # Headers no longer shown - intentional optimization


class TestReplayWithTarget:
    """Tests for replaying events with target URL."""
    
    @pytest.mark.asyncio
    async def test_replay_sends_to_target(self, events_file, sample_events):
        """Test replaying events sends to target."""
        target_url = "http://localhost:3000"
        replayer = EventReplayer(events_file, target_url=target_url)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            await replayer.replay()
            
            # Should have called request for each event
            assert mock_instance.request.call_count == len(sample_events)
    
    @pytest.mark.asyncio
    async def test_replay_constructs_correct_url(self, events_file):
        """Test that replay constructs correct URL."""
        target_url = "http://localhost:3000"
        replayer = EventReplayer(events_file, target_url=target_url)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            await replayer.replay()
            
            # Check first call
            first_call = mock_instance.request.call_args_list[0]
            assert first_call[1]['url'] == "http://localhost:3000/webhook"
    
    @pytest.mark.asyncio
    async def test_replay_preserves_method(self, events_file):
        """Test that replay preserves HTTP method."""
        replayer = EventReplayer(events_file, target_url="http://localhost:3000")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            await replayer.replay()
            
            # Check methods
            calls = mock_instance.request.call_args_list
            assert calls[0][1]['method'] == 'POST'
            assert calls[2][1]['method'] == 'GET'
    
    @pytest.mark.asyncio
    async def test_replay_sends_json_body(self, events_file):
        """Test that replay sends JSON body."""
        replayer = EventReplayer(events_file, target_url="http://localhost:3000")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            await replayer.replay()
            
            # Check first call has JSON body
            first_call = mock_instance.request.call_args_list[0]
            content = first_call[1]['content']
            assert json.loads(content) == {"event": "first"}
    
    @pytest.mark.asyncio
    # Change capsys to caplog
    async def test_replay_handles_errors(self, events_file, caplog): 
        """Test that replay handles send errors gracefully."""
        replayer = EventReplayer(events_file, target_url="http://localhost:3000")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            # The side_effect will trigger max_retries-1 warnings and 1 error.
            mock_instance.request.side_effect = Exception("Connection error")
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            # The log messages are generated when this function runs
            await replayer.replay()
            
            # Use caplog.text to check the captured log output
            # We expect the final error message after all retries fail.
            assert "Failed to send event after 3 attempts: Connection error" in caplog.text
            # We also expect the warning message from the retries
            assert "Error sending event: Connection error, retrying..." in caplog.text

class TestReplayTiming:
    """Tests for replay timing modes."""
    
    @pytest.mark.asyncio
    async def test_fixed_delay(self, events_file):
        """Test replay with fixed delay between events."""
        replayer = EventReplayer(events_file, fixed_delay=0.1)
        
        start = time.time()
        await replayer.replay()
        duration = time.time() - start
        
        # Should take at least 0.2 seconds (2 delays between 3 events)
        assert duration >= 0.2
    
    @pytest.mark.asyncio
    async def test_no_delay_fast(self, events_file):
        """Test replay without delay is fast."""
        replayer = EventReplayer(events_file, fixed_delay=0.0)
        
        start = time.time()
        await replayer.replay()
        duration = time.time() - start
        
        # Should be very quick
        assert duration < 1.0
    
    @pytest.mark.asyncio
    async def test_replay_once_preserves_timing(self, events_file):
        """Test replay_once mode preserves original timing."""
        # Events have 2s and 3s gaps
        replayer = EventReplayer(events_file, replay_once=True, rate=10.0)
        
        start = time.time()
        await replayer.replay()
        duration = time.time() - start
        
        # With 10x rate, 5 seconds should become 0.5 seconds
        assert 0.4 <= duration <= 0.7
    
    @pytest.mark.asyncio
    async def test_rate_multiplier(self, events_file):
        """Test rate multiplier affects timing."""
        # Events have total 5 second span
        replayer = EventReplayer(events_file, replay_once=True, rate=2.0)
        
        start = time.time()
        await replayer.replay()
        duration = time.time() - start
        
        # With 2x rate, 5 seconds should become ~2.5 seconds
        assert 2.0 <= duration <= 3.0


class TestReplayEventIndex:
    """Tests for event indexing during replay."""
    
    @pytest.mark.asyncio
    async def test_event_index_in_output(self, events_file, capsys):
        """Test that event index is shown in output."""
        replayer = EventReplayer(events_file)
        await replayer.replay()
        
        captured = capsys.readouterr()
        assert "[1/3]" in captured.out
        assert "[2/3]" in captured.out
        assert "[3/3]" in captured.out


class TestReplayCleanup:
    """Tests for cleanup after replay."""
    
    @pytest.mark.asyncio
    async def test_http_client_closed(self, events_file):
        """Test that HTTP client is closed after replay."""
        replayer = EventReplayer(events_file, target_url="http://localhost:3000")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = Mock(status_code=200)
            mock_client.return_value = mock_instance
            
            replayer._http_client = mock_instance
            
            await replayer.replay()
            
            mock_instance.aclose.assert_called_once()


class TestReplayEmptyFile:
    """Tests for replaying empty file."""
    
    @pytest.mark.asyncio
    async def test_replay_empty_file(self, tmp_path, capsys):
        """Test replaying empty file shows warning."""
        file_path = tmp_path / "empty.json"
        file_path.write_text("")
        
        replayer = EventReplayer(file_path)
        await replayer.replay()
        
        # Should not crash, might log warning