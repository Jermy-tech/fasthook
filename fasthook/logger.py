"""Event logging and forwarding functionality."""

import json
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
import httpx

from .utils import pretty_print


class EventLogger:
    """Handles logging, saving, and forwarding of webhook events."""
    
    def __init__(
        self,
        save_path: Optional[str] = None,
        forward_url: Optional[str] = None,
        pretty: bool = False,
        quiet: bool = False
    ):
        """Initialize the EventLogger.
        
        Args:
            save_path: Path to JSON file for saving events
            forward_url: URL to forward requests to
            pretty: Pretty-print JSON output to console
            quiet: Suppress console output except errors
        """
        self.save_path = save_path
        self.forward_url = forward_url
        self.pretty = pretty
        self.quiet = quiet
        self._file_lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None
        
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for forwarding requests."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def log(self, event: Dict[str, Any]) -> None:
        """Log a webhook event.
        
        Args:
            event: Dictionary containing event details
        """
        if not self.quiet:
            await self._print_event(event)
        
        if self.save_path:
            await self._save_event(event)
        
        if self.forward_url:
            await self._forward_event(event)
    
    async def _print_event(self, event: Dict[str, Any]) -> None:
        """Print event to console."""
        try:
            print("\n" + "="*60)
            print(f"[{event['timestamp']}] {event['method']} {event['path']}")
            print(f"IP: {event['ip']}")
            
            if event['query']:
                print(f"Query: {event['query']}")
            
            if event['headers']:
                print("Headers:")
                for key, value in event['headers'].items():
                    print(f"  {key}: {value}")
            
            if event['json']:
                print("JSON Body:")
                if self.pretty:
                    pretty_print(event['json'])
                else:
                    print(f"  {json.dumps(event['json'])}")
            elif event['raw']:
                print(f"Raw Body: {event['raw'][:500]}")
            
            print("="*60)
        except Exception as e:
            print(f"Error printing event: {e}")
    
    async def _save_event(self, event: Dict[str, Any]) -> None:
        """Save event to JSON file (newline-delimited)."""
        try:
            async with self._file_lock:
                path = Path(self.save_path)
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(event) + '\n')
        except Exception as e:
            print(f"Error saving event: {e}")
    
    async def _forward_event(self, event: Dict[str, Any]) -> None:
        """Forward the request to the configured URL."""
        try:
            client = await self._get_http_client()
            
            method = event['method']
            headers = event['headers'].copy()
            headers.pop('host', None)
            
            body = None
            if event['json']:
                body = json.dumps(event['json'])
                headers['content-type'] = 'application/json'
            elif event['raw']:
                body = event['raw']
            
            response = await client.request(
                method=method,
                url=self.forward_url,
                headers=headers,
                content=body
            )
            
            if not self.quiet:
                print(f"↪️  Forwarded to {self.forward_url}: {response.status_code}")
                
        except Exception as e:
            print(f"Error forwarding event: {e}")
    
    async def close(self) -> None:
        """Close HTTP client if it exists."""
        if self._http_client:
            await self._http_client.aclose()
