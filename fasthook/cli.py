"""Command-line interface for fasthook."""

import click
import uvicorn
from typing import Optional

from .server import create_app
from .logger import EventLogger


@click.group()
def main():
    """fasthook - A simple local webhook receiver and relay tool."""
    pass


@main.command()
@click.argument("port", type=int)
@click.option("--save", type=str, default=None, help="Save events to JSON file")
@click.option("--forward", type=str, default=None, help="Forward requests to this URL")
@click.option("--pretty", is_flag=True, help="Pretty-print JSON to console")
@click.option("--quiet", is_flag=True, help="Suppress console output except errors")
@click.option("--host", type=str, default="127.0.0.1", help="Host to bind to")
@click.option("--debug", is_flag=True, help="Run in debug mode")
def listen(
    port: int,
    save: Optional[str],
    forward: Optional[str],
    pretty: bool,
    quiet: bool,
    host: str,
    debug: bool
):
    """Start the webhook listener on the specified PORT.
    
    Examples:
        fasthook listen 3000
        fasthook listen 3000 --save events.json
        fasthook listen 3000 --forward http://example.com/webhook
        fasthook listen 3000 --save events.json --forward http://example.com/webhook --pretty
    """
    logger = EventLogger(
        save_path=save,
        forward_url=forward,
        pretty=pretty,
        quiet=quiet
    )
    
    app = create_app(logger)
    
    if not quiet:
        click.echo(f"🚀 fasthook listening on http://{host}:{port}")
        if save:
            click.echo(f"💾 Saving events to: {save}")
        if forward:
            click.echo(f"↪️  Forwarding to: {forward}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="error" if quiet else "info",
        access_log=not quiet
    )


if __name__ == "__main__":
    main()
