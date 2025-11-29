"""Command-line interface - OPTIMIZED & PRODUCTION-READY."""

import click
import uvicorn
import json
import asyncio
import os
from pathlib import Path
from typing import Optional

from .server import create_app
from .logger import EventLogger, Logger, Forwarder, EventCoordinator
from .mock import MockServer
from .replay import EventReplayer


@click.group()
@click.version_option(version="2.0.0", prog_name="fasthook")
def main():
    """fasthook - A high-performance local webhook receiver and relay tool.
    
    OPTIMIZED: Added version option.
    """
    pass


@main.command()
@click.argument("port", type=int)
@click.option("--save", type=str, default=None, help="Save events to JSON file")
@click.option("--forward", type=str, default=None, help="Forward requests to this URL")
@click.option("--forward-retries", type=int, default=3, help="Number of forward retry attempts")
@click.option("--forward-concurrency", type=int, default=5, help="Max concurrent forward requests")
@click.option("--pretty", is_flag=True, help="Pretty-print JSON to console")
@click.option("--quiet", is_flag=True, help="Suppress console output except errors")
@click.option("--host", type=str, default="127.0.0.1", help="Host to bind to")
@click.option("--debug", is_flag=True, help="Run in debug mode")
@click.option("--log-file", type=str, default=None, help="Log application logs to file")
@click.option("--log-level", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='INFO', help="Set logging level")
@click.option("--log-rotate", is_flag=True, help="Enable log file rotation")
@click.option("--exit-after", type=int, default=None, help="Exit after N events (useful for CI)")
@click.option("--mock", type=str, default=None, help="Run in mock mode with response spec file")
def listen(
    port: int,
    save: Optional[str],
    forward: Optional[str],
    forward_retries: int,
    forward_concurrency: int,
    pretty: bool,
    quiet: bool,
    host: str,
    debug: bool,
    log_file: Optional[str],
    log_level: str,
    log_rotate: bool,
    exit_after: Optional[int],
    mock: Optional[str]
):
    """Start the webhook listener on the specified PORT.
    
    OPTIMIZED:
    - Better validation
    - Early error detection
    - Clearer messages
    
    Examples:
        fasthook listen 3000
        fasthook listen 3000 --save events.json
        fasthook listen 3000 --forward http://example.com/webhook
        fasthook listen 3000 --save events.json --forward http://example.com/webhook --pretty
        fasthook listen 3000 --mock responses.json
        fasthook listen 3000 --exit-after 10 --quiet
    """
    # OPTIMIZATION: Validate port range
    if not (1 <= port <= 65535):
        click.echo(f"Error: Port must be between 1 and 65535, got {port}", err=True)
        return
    
    # OPTIMIZATION: Validate save path early
    if save:
        save_path = Path(save)
        
        # Check if parent directory exists
        if not save_path.parent.exists():
            click.echo(f"Error: Directory does not exist: {save_path.parent}", err=True)
            return
        
        # Check if file exists and is writable
        if save_path.exists() and not os.access(save_path, os.W_OK):
            click.echo(f"Error: Cannot write to file: {save_path}", err=True)
            return
    
    # Check for conflicting flags
    active_modes = [bool(save), bool(forward), bool(mock)]
    if not any(active_modes) and quiet:
        click.echo("Warning: --quiet specified but no output/save/forward enabled", err=True)
    
    # Convert save path to Path object
    save_path = Path(save) if save else None
    
    # Setup logger and forwarder
    logger_obj = Logger(
        save_path=save_path,
        pretty=pretty,
        quiet=quiet,
        log_file=log_file,
        log_level=log_level,
        log_rotate=log_rotate
    )
    
    forwarder_obj = None
    if forward:
        forwarder_obj = Forwarder(
            forward_url=forward,
            forward_retries=forward_retries,
            forward_concurrency=forward_concurrency,
            quiet=quiet
        )
    
    coordinator = EventCoordinator(logger_obj, forwarder_obj)
    
    # Legacy wrapper for compatibility
    event_logger = EventLogger(
        save_path=save_path,
        forward_url=forward,
        forward_retries=forward_retries,
        forward_concurrency=forward_concurrency,
        pretty=pretty,
        quiet=quiet
    )
    
    # Create appropriate app
    if mock:
        try:
            mock_server = MockServer.from_file(Path(mock))
            app = mock_server.create_app()
            if not quiet:
                click.echo(f"🎭 fasthook running in MOCK mode on http://{host}:{port}")
                click.echo(f"📋 Using spec: {mock}")
                click.echo(f"💡 Stats available at: http://{host}:{port}/__mock__/stats")
        except Exception as e:
            click.echo(f"❌ Error loading mock spec: {e}", err=True)
            return
    else:
        app = create_app(event_logger, exit_after=exit_after)
        
        if not quiet:
            click.echo(f"🚀 fasthook listening on http://{host}:{port}")
            if save:
                click.echo(f"💾 Saving events to: {save}")
            if forward:
                click.echo(f"↪️  Forwarding to: {forward}")
                click.echo(f"🔄 Retries: {forward_retries}, Concurrency: {forward_concurrency}")
            if exit_after:
                click.echo(f"ℹ️  Will exit after {exit_after} events")
            click.echo(f"🏥 Health check: http://{host}:{port}/health")
            click.echo()
            click.echo("Press Ctrl+C to stop")
    
    # OPTIMIZATION: Better uvicorn configuration
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="error" if quiet else ("debug" if debug else "info"),
            access_log=not quiet,
            # OPTIMIZATION: Better performance settings
            timeout_keep_alive=5,
            limit_concurrency=1000,
            limit_max_requests=None,
        )
    except KeyboardInterrupt:
        if not quiet:
            click.echo("\n\n👋 Shutting down gracefully...")
    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        raise


@main.command()
@click.argument("events_file", type=click.Path(exists=True))
@click.option("--rate", type=float, default=1.0, help="Playback rate multiplier (1.0 = real-time)")
@click.option("--once", is_flag=True, help="Replay events only once, preserving timing")
@click.option("--target", type=str, default=None, help="Target URL to replay events to")
@click.option("--delay", type=float, default=0.0, help="Fixed delay between events (seconds)")
@click.option("--max-rps", type=float, default=100.0, help="Maximum requests per second (default: 100)")
def replay(
    events_file: str,
    rate: float,
    once: bool,
    target: Optional[str],
    delay: float,
    max_rps: float
):
    """Replay saved webhook events.
    
    OPTIMIZED:
    - Added max-rps option
    - Better progress reporting
    - Validation
    
    Examples:
        fasthook replay events.json
        fasthook replay events.json --rate 2.0
        fasthook replay events.json --target http://localhost:3000
        fasthook replay events.json --delay 1.0 --once
        fasthook replay events.json --max-rps 50
    """
    # OPTIMIZATION: Validate parameters
    if rate <= 0:
        click.echo("Error: --rate must be positive", err=True)
        return
    
    if delay < 0:
        click.echo("Error: --delay cannot be negative", err=True)
        return
    
    if max_rps <= 0:
        click.echo("Error: --max-rps must be positive", err=True)
        return
    
    # Check if file exists and is readable
    file_path = Path(events_file)
    if not file_path.exists():
        click.echo(f"Error: File not found: {events_file}", err=True)
        return
    
    if not os.access(file_path, os.R_OK):
        click.echo(f"Error: Cannot read file: {events_file}", err=True)
        return
    
    replayer = EventReplayer(
        events_file=file_path,
        rate=rate,
        target_url=target,
        fixed_delay=delay,
        replay_once=once,
        max_rps=max_rps
    )
    
    click.echo(f"🔄 Replaying events from: {events_file}")
    if target:
        click.echo(f"🎯 Target URL: {target}")
    if rate != 1.0:
        click.echo(f"⏩ Playback rate: {rate}x")
    if delay > 0:
        click.echo(f"⏱️  Fixed delay: {delay}s between events")
    if max_rps != 100.0:
        click.echo(f"🚦 Rate limit: {max_rps} requests/second")
    click.echo()
    
    try:
        asyncio.run(replayer.replay())
    except KeyboardInterrupt:
        click.echo("\n\n⏸️  Replay interrupted")
    except Exception as e:
        click.echo(f"\n❌ Replay error: {e}", err=True)
        raise


@main.command()
@click.argument("port", type=int)
@click.option("--spec", type=click.Path(exists=True), required=True, help="Mock response specification file")
@click.option("--host", type=str, default="127.0.0.1", help="Host to bind to")
@click.option("--quiet", is_flag=True, help="Suppress console output")
def mock(port: int, spec: str, host: str, quiet: bool):
    """Start a mock webhook server with scripted responses.
    
    OPTIMIZED:
    - Better error messages
    - Validation
    
    Examples:
        fasthook mock 3000 --spec responses.json
        
    Spec file format (JSON or YAML):
    {
        "defaults": {
            "status": 200,
            "delay": 0
        },
        "routes": {
            "/webhook": {
                "POST": {
                    "status": 201,
                    "body": {"success": true},
                    "delay": 0.5
                }
            }
        }
    }
    """
    # Validate port
    if not (1 <= port <= 65535):
        click.echo(f"Error: Port must be between 1 and 65535, got {port}", err=True)
        return
    
    try:
        mock_server = MockServer.from_file(Path(spec))
        app = mock_server.create_app()
        
        if not quiet:
            click.echo(f"🎭 Mock server running on http://{host}:{port}")
            click.echo(f"📋 Using spec: {spec}")
            click.echo(f"📊 Stats: http://{host}:{port}/__mock__/stats")
            click.echo(f"🔄 Reset: http://{host}:{port}/__mock__/reset")
            click.echo(f"🏥 Health: http://{host}:{port}/__mock__/health")
            click.echo()
            click.echo("Press Ctrl+C to stop")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="error" if quiet else "info",
            access_log=not quiet,
            timeout_keep_alive=5
        )
    except KeyboardInterrupt:
        if not quiet:
            click.echo("\n\n👋 Mock server stopped")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise


if __name__ == "__main__":
    main()