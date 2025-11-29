"""Tests for CLI module - FIXED VERSION"""

import pytest
import json
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, Mock, MagicMock, AsyncMock

from fasthook.cli import main, listen, replay, mock


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_events_file(tmp_path):
    """Create a sample events file."""
    file_path = tmp_path / "events.json"
    events = [
        {
            "timestamp": "2024-01-01T12:00:00Z",
            "method": "POST",
            "path": "/webhook",
            "headers": {},
            "query": {},
            "json": {"test": "data"},
            "raw": "",
            "ip": "127.0.0.1"
        }
    ]
    with open(file_path, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')
    return file_path


@pytest.fixture
def mock_spec_file(tmp_path):
    """Create a mock spec file."""
    file_path = tmp_path / "spec.json"
    spec = {
        "defaults": {"status": 200},
        "routes": {
            "/webhook": {
                "POST": {"status": 201, "body": {"ok": True}}
            }
        }
    }
    with open(file_path, 'w') as f:
        json.dump(spec, f)
    return file_path


class TestMainCommand:
    """Tests for main CLI command."""
    
    def test_main_help(self, runner):
        """Test main command help."""
        result = runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'fasthook' in result.output
    
    def test_main_no_args(self, runner):
        """Test main command without arguments shows help."""
        result = runner.invoke(main)
        # Click group without subcommand returns exit code 0 and shows usage
        assert result.exit_code in [0, 2]  # 0 for help shown, 2 for missing command


class TestListenCommand:
    """Tests for listen command."""
    
    def test_listen_help(self, runner):
        """Test listen command help."""
        result = runner.invoke(listen, ['--help'])
        assert result.exit_code == 0
        assert 'PORT' in result.output
        assert '--save' in result.output
        assert '--forward' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_basic(self, mock_uvicorn, runner):
        """Test basic listen command."""
        result = runner.invoke(listen, ['3000'])
        assert result.exit_code == 0
        
        # Verify uvicorn was called
        mock_uvicorn.assert_called_once()
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['port'] == 3000
        assert call_kwargs['host'] == '127.0.0.1'
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_save(self, mock_uvicorn, runner, tmp_path):
        """Test listen with --save option."""
        save_path = tmp_path / "events.json"
        result = runner.invoke(listen, ['3000', '--save', str(save_path)])
        assert result.exit_code == 0
        assert 'Saving events to:' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_forward(self, mock_uvicorn, runner):
        """Test listen with --forward option."""
        result = runner.invoke(listen, ['3000', '--forward', 'http://example.com'])
        assert result.exit_code == 0
        assert 'Forwarding to:' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_pretty(self, mock_uvicorn, runner):
        """Test listen with --pretty flag."""
        result = runner.invoke(listen, ['3000', '--pretty'])
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_quiet(self, mock_uvicorn, runner):
        """Test listen with --quiet flag."""
        result = runner.invoke(listen, ['3000', '--quiet'])
        assert result.exit_code == 0
        # Should have minimal output
        assert 'fasthook listening' not in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_custom_host(self, mock_uvicorn, runner):
        """Test listen with custom host."""
        result = runner.invoke(listen, ['3000', '--host', '0.0.0.0'])
        assert result.exit_code == 0
        
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['host'] == '0.0.0.0'
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_debug_mode(self, mock_uvicorn, runner):
        """Test listen with --debug flag."""
        result = runner.invoke(listen, ['3000', '--debug'])
        assert result.exit_code == 0
        
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['log_level'] == 'debug'
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_log_file(self, mock_uvicorn, runner, tmp_path):
        """Test listen with --log-file option."""
        log_file = tmp_path / "app.log"
        result = runner.invoke(listen, ['3000', '--log-file', str(log_file)])
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_log_level(self, mock_uvicorn, runner):
        """Test listen with --log-level option."""
        result = runner.invoke(listen, ['3000', '--log-level', 'DEBUG'])
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_log_rotate(self, mock_uvicorn, runner, tmp_path):
        """Test listen with --log-rotate flag."""
        log_file = tmp_path / "app.log"
        result = runner.invoke(listen, [
            '3000',
            '--log-file', str(log_file),
            '--log-rotate'
        ])
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_exit_after(self, mock_uvicorn, runner):
        """Test listen with --exit-after option."""
        result = runner.invoke(listen, ['3000', '--exit-after', '10'])
        assert result.exit_code == 0
        assert 'Will exit after 10 events' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_forward_retries(self, mock_uvicorn, runner):
        """Test listen with --forward-retries option."""
        result = runner.invoke(listen, [
            '3000',
            '--forward', 'http://example.com',
            '--forward-retries', '5'
        ])
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_with_forward_concurrency(self, mock_uvicorn, runner):
        """Test listen with --forward-concurrency option."""
        result = runner.invoke(listen, [
            '3000',
            '--forward', 'http://example.com',
            '--forward-concurrency', '10'
        ])
        assert result.exit_code == 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_quiet_warning(self, mock_uvicorn, runner):
        """Test warning when --quiet without save/forward."""
        result = runner.invoke(listen, ['3000', '--quiet'])
        assert result.exit_code == 0
        assert 'Warning' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_mock_mode(self, mock_uvicorn, runner, mock_spec_file):
        """Test listen in mock mode."""
        result = runner.invoke(listen, ['3000', '--mock', str(mock_spec_file)])
        assert result.exit_code == 0
        assert 'MOCK mode' in result.output
        assert 'Using spec:' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_mock_mode_invalid_spec(self, mock_uvicorn, runner, tmp_path):
        """Test listen with invalid mock spec file."""
        invalid_spec = tmp_path / "invalid.json"
        invalid_spec.write_text("not valid json")
        
        result = runner.invoke(listen, ['3000', '--mock', str(invalid_spec)])
        assert result.exit_code == 0
        assert 'Error loading mock spec' in result.output


class TestReplayCommand:
    """Tests for replay command."""
    
    def test_replay_help(self, runner):
        """Test replay command help."""
        result = runner.invoke(replay, ['--help'])
        assert result.exit_code == 0
        assert 'EVENTS_FILE' in result.output
        assert '--rate' in result.output
        assert '--target' in result.output
    
    def test_replay_basic(self, runner, sample_events_file):
        """Test basic replay command."""
        # Mock the EventReplayer.replay method instead of asyncio.run
        with patch('fasthook.cli.EventReplayer') as mock_replayer_class:
            mock_instance = Mock()
            mock_instance.replay = AsyncMock()
            mock_replayer_class.return_value = mock_instance
            
            result = runner.invoke(replay, [str(sample_events_file)])
            assert result.exit_code == 0
            assert 'Replaying events from:' in result.output
            
            # Verify EventReplayer was instantiated
            mock_replayer_class.assert_called_once()
    
    def test_replay_with_rate(self, runner, sample_events_file):
        """Test replay with --rate option."""
        # Mock the EventReplayer.replay method instead of asyncio.run
        with patch('fasthook.cli.EventReplayer') as mock_replayer_class:
            mock_instance = Mock()
            mock_instance.replay = AsyncMock()
            mock_replayer_class.return_value = mock_instance
            
            result = runner.invoke(replay, [str(sample_events_file), '--rate', '2.0'])
            assert result.exit_code == 0
            assert 'Playback rate: 2.0x' in result.output
    
    def test_replay_with_target(self, runner, sample_events_file):
        """Test replay with --target option."""
        # Mock the EventReplayer.replay method instead of asyncio.run
        with patch('fasthook.cli.EventReplayer') as mock_replayer_class:
            mock_instance = Mock()
            mock_instance.replay = AsyncMock()
            mock_replayer_class.return_value = mock_instance
            
            result = runner.invoke(replay, [
                str(sample_events_file),
                '--target', 'http://localhost:3000'
            ])
            assert result.exit_code == 0
            assert 'Target URL: http://localhost:3000' in result.output
            
            mock_replayer_class.assert_called_once()
    
    def test_replay_with_delay(self, runner, sample_events_file):
        """Test replay with --delay option."""
        # Mock the EventReplayer.replay method instead of asyncio.run
        with patch('fasthook.cli.EventReplayer') as mock_replayer_class:
            mock_instance = Mock()
            mock_instance.replay = AsyncMock()
            mock_replayer_class.return_value = mock_instance
            
            result = runner.invoke(replay, [
                str(sample_events_file),
                '--delay', '1.0'
            ])
            assert result.exit_code == 0
            assert 'Fixed delay: 1.0s' in result.output
            
            # Verify the replayer was configured correctly
            mock_replayer_class.assert_called_once()
    
    def test_replay_once(self, runner, sample_events_file):
        """Test replay with --once flag."""
        # Mock the EventReplayer.replay method instead of asyncio.run
        with patch('fasthook.cli.EventReplayer') as mock_replayer_class:
            mock_instance = Mock()
            mock_instance.replay = AsyncMock()
            mock_replayer_class.return_value = mock_instance
            
            result = runner.invoke(replay, [
                str(sample_events_file),
                '--once'
            ])
            assert result.exit_code == 0
    
    def test_replay_nonexistent_file(self, runner):
        """Test replay with nonexistent file."""
        result = runner.invoke(replay, ['nonexistent.json'])
        assert result.exit_code != 0
        assert 'does not exist' in result.output.lower() or 'Error' in result.output


class TestMockCommand:
    """Tests for mock command."""
    
    def test_mock_help(self, runner):
        """Test mock command help."""
        result = runner.invoke(mock, ['--help'])
        assert result.exit_code == 0
        assert 'PORT' in result.output
        assert '--spec' in result.output
    
    @patch('fasthook.cli.uvicorn.run')
    def test_mock_basic(self, mock_uvicorn, runner, mock_spec_file):
        """Test basic mock command."""
        result = runner.invoke(mock, ['3000', '--spec', str(mock_spec_file)])
        assert result.exit_code == 0
        assert 'Mock server running' in result.output
        assert 'Using spec:' in result.output
        
        # Verify uvicorn was called
        mock_uvicorn.assert_called_once()
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['port'] == 3000
    
    @patch('fasthook.cli.uvicorn.run')
    def test_mock_custom_host(self, mock_uvicorn, runner, mock_spec_file):
        """Test mock with custom host."""
        result = runner.invoke(mock, [
            '3000',
            '--spec', str(mock_spec_file),
            '--host', '0.0.0.0'
        ])
        assert result.exit_code == 0
        
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['host'] == '0.0.0.0'
    
    @patch('fasthook.cli.uvicorn.run')
    def test_mock_quiet(self, mock_uvicorn, runner, mock_spec_file):
        """Test mock with --quiet flag."""
        result = runner.invoke(mock, [
            '3000',
            '--spec', str(mock_spec_file),
            '--quiet'
        ])
        assert result.exit_code == 0
        assert 'Mock server running' not in result.output
    
    def test_mock_missing_spec(self, runner):
        """Test mock without --spec option."""
        result = runner.invoke(mock, ['3000'])
        assert result.exit_code != 0
        assert 'required' in result.output.lower() or 'Missing' in result.output
    
    def test_mock_invalid_spec(self, runner, tmp_path):
        """Test mock with invalid spec file."""
        invalid_spec = tmp_path / "invalid.json"
        invalid_spec.write_text("not valid json")
        
        result = runner.invoke(mock, ['3000', '--spec', str(invalid_spec)])
        # FIXED: Optimized code properly returns exit code 1 on error
        assert result.exit_code != 0
        assert 'Error' in result.output or 'Invalid' in str(result.exception)


class TestCLIIntegration:
    """Integration tests for CLI commands."""
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_all_options(self, mock_uvicorn, runner, tmp_path):
        """Test listen with multiple options combined."""
        save_path = tmp_path / "events.json"
        log_path = tmp_path / "app.log"
        
        result = runner.invoke(listen, [
            '3000',
            '--save', str(save_path),
            '--forward', 'http://example.com',
            '--forward-retries', '5',
            '--forward-concurrency', '10',
            '--pretty',
            '--host', '0.0.0.0',
            '--debug',
            '--log-file', str(log_path),
            '--log-level', 'DEBUG',
            '--log-rotate',
            '--exit-after', '100'
        ])
        
        assert result.exit_code == 0
        mock_uvicorn.assert_called_once()
    
    def test_replay_all_options(self, runner, sample_events_file):
        """Test replay with all options combined."""
        # Mock the EventReplayer.replay method instead of asyncio.run
        with patch('fasthook.cli.EventReplayer') as mock_replayer_class:
            mock_instance = Mock()
            mock_instance.replay = AsyncMock()
            mock_replayer_class.return_value = mock_instance
            
            result = runner.invoke(replay, [
                str(sample_events_file),
                '--rate', '2.0',
                '--once',
                '--target', 'http://localhost:3000',
                '--delay', '0.5'
            ])
            
            assert result.exit_code == 0
            mock_replayer_class.assert_called_once()


class TestCLIValidation:
    """Tests for CLI argument validation."""
    
    def test_listen_invalid_port(self, runner):
        """Test listen with invalid port number."""
        result = runner.invoke(listen, ['invalid'])
        assert result.exit_code != 0
    
    @patch('fasthook.cli.uvicorn.run')
    def test_listen_invalid_log_level(self, mock_uvicorn, runner):
        """Test listen with invalid log level."""
        result = runner.invoke(listen, ['3000', '--log-level', 'INVALID'])
        assert result.exit_code != 0
    
    def test_replay_invalid_rate(self, runner, sample_events_file):
        """Test replay with invalid rate."""
        result = runner.invoke(replay, [str(sample_events_file), '--rate', 'invalid'])
        assert result.exit_code != 0
    
    def test_replay_invalid_delay(self, runner, sample_events_file):
        """Test replay with invalid delay."""
        result = runner.invoke(replay, [str(sample_events_file), '--delay', 'invalid'])
        assert result.exit_code != 0