"""Event logging and forwarding functionality - OPTIMIZED VERSION."""

import json
import asyncio
import logging
from typing import Optional, Dict, Any, Union, IO
from pathlib import Path
from logging.handlers import RotatingFileHandler
import httpx

from .utils import pretty_print


class Logger:
    """Handles logging and saving of webhook events."""
    
    def __init__(
        self,
        save_path: Optional[Union[str, Path, IO]] = None,
        pretty: bool = False,
        quiet: bool = False,
        log_file: Optional[Union[str, Path]] = None,
        log_level: str = "INFO",
        log_rotate: bool = False
    ):
        """Initialize the Logger."""
        self.save_path = Path(save_path) if isinstance(save_path, str) else save_path
        self.pretty = pretty
        self.quiet = quiet
        self._file_lock = asyncio.Lock()
        
        # Setup Python logging
        self.logger = logging.getLogger("fasthook")
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Console handler
        if not quiet:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # File handler with optional rotation
        if log_file:
            log_path = Path(log_file)
            if log_rotate:
                file_handler = RotatingFileHandler(
                    log_path,
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                )
            else:
                file_handler = logging.FileHandler(log_path)
            
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    async def log_event(self, event: Dict[str, Any]) -> None:
        """Log a webhook event."""
        if not self.quiet:
            await self._print_event(event)
        
        if self.save_path:
            await self._save_event(event)
    
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
            self.logger.error(f"Error printing event: {e}")
    
    async def _save_event(self, event: Dict[str, Any]) -> None:
        """Save event to JSON file or file-like object (newline-delimited)."""
        try:
            async with self._file_lock:
                event_json = json.dumps(event) + '\n'
                
                if isinstance(self.save_path, Path):
                    # OPTIMIZED: Use asyncio.to_thread for file I/O to avoid blocking
                    await asyncio.to_thread(self._write_to_file, event_json)
                elif hasattr(self.save_path, 'write'):
                    # Write to file-like object (IO)
                    if hasattr(self.save_path, 'mode') and 'b' in self.save_path.mode:
                        self.save_path.write(event_json.encode('utf-8'))
                    else:
                        self.save_path.write(event_json)
                    if hasattr(self.save_path, 'flush'):
                        self.save_path.flush()
        except Exception as e:
            self.logger.error(f"Error saving event: {e}")
    
    def _write_to_file(self, content: str) -> None:
        """Synchronous file write (called via to_thread)."""
        with open(self.save_path, 'a', encoding='utf-8') as f:
            f.write(content)


class Forwarder:
    """Handles forwarding of webhook events to another URL.
    
    OPTIMIZED with:
    - Bounded queue to prevent memory leaks
    - Connection pooling for better performance
    - Proper resource cleanup
    """
    
    # CRITICAL FIX: Add maximum queue size
    MAX_QUEUE_SIZE = 1000
    
    def __init__(
        self,
        forward_url: Optional[str] = None,
        forward_retries: int = 3,
        forward_concurrency: int = 5,
        quiet: bool = False
    ):
        """Initialize the Forwarder."""
        self.forward_url = forward_url
        self.forward_retries = forward_retries
        self.forward_concurrency = forward_concurrency
        self.quiet = quiet
        self.logger = logging.getLogger("fasthook.forwarder")
        
        self._http_client: Optional[httpx.AsyncClient] = None
        self._forward_queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        
        if forward_url:
            # CRITICAL FIX: Bounded queue prevents memory leaks
            self._forward_queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
            self._semaphore = asyncio.Semaphore(forward_concurrency)
    
    async def start(self) -> None:
        """Start the forwarding worker."""
        if self.forward_url and not self._worker_task:
            self._worker_task = asyncio.create_task(self._forward_worker())
    
    async def stop(self) -> None:
        """Stop the forwarding worker and cleanup."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        if self._http_client:
            await self._http_client.aclose()
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for forwarding requests.
        
        OPTIMIZED: Added connection pooling limits.
        """
        if self._http_client is None:
            # OPTIMIZATION: Configure connection pooling
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                    keepalive_expiry=30.0
                )
            )
        return self._http_client
    
    async def forward_event(self, event: Dict[str, Any]) -> None:
        """Queue an event for forwarding.
        
        OPTIMIZED: Handles queue full scenario gracefully.
        """
        if self.forward_url and self._forward_queue:
            try:
                # CRITICAL FIX: Handle queue full with timeout
                await asyncio.wait_for(
                    self._forward_queue.put(event),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                self.logger.error(
                    f"Forward queue full (size: {self.MAX_QUEUE_SIZE}), dropping event"
                )
                # Optionally: implement fallback strategy (e.g., save to disk)
    
    async def _forward_worker(self) -> None:
        """Worker that processes the forward queue."""
        while True:
            try:
                event = await self._forward_queue.get()
                await self._process_forward(event)
                self._forward_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in forward worker: {e}")
    
    async def _process_forward(self, event: Dict[str, Any]) -> None:
        """Process a single forward request with retries."""
        async with self._semaphore:
            for attempt in range(self.forward_retries):
                try:
                    await self._forward_request(event)
                    break
                except Exception as e:
                    if attempt == self.forward_retries - 1:
                        self.logger.error(f"Failed to forward after {self.forward_retries} attempts: {e}")
                    else:
                        # Exponential backoff
                        await asyncio.sleep(2 ** attempt)
    
    async def _forward_request(self, event: Dict[str, Any]) -> None:
        """Forward a single request to the configured URL."""
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
            self.logger.info(f"Forwarded to {self.forward_url}: {response.status_code}")


class EventCoordinator:
    """Coordinates logging and forwarding of webhook events."""
    
    def __init__(self, logger: Logger, forwarder: Optional[Forwarder] = None):
        """Initialize the EventCoordinator."""
        self.logger = logger
        self.forwarder = forwarder
    
    async def start(self) -> None:
        """Start the coordinator and its components."""
        if self.forwarder:
            await self.forwarder.start()
    
    async def stop(self) -> None:
        """Stop the coordinator and cleanup resources."""
        if self.forwarder:
            await self.forwarder.stop()
    
    async def handle_event(self, event: Dict[str, Any]) -> None:
        """Handle a webhook event by logging and optionally forwarding it."""
        # Log the event
        await self.logger.log_event(event)
        
        # Forward if configured
        if self.forwarder:
            await self.forwarder.forward_event(event)


# Backward compatibility wrapper
class EventLogger:
    """Legacy EventLogger for backward compatibility."""
    
    def __init__(
        self,
        save_path: Optional[Union[str, Path, IO]] = None,
        forward_url: Optional[str] = None,
        pretty: bool = False,
        quiet: bool = False,
        forward_retries: int = 3,
        forward_concurrency: int = 5
    ):
        """Initialize the EventLogger (legacy interface)."""
        self.logger = Logger(save_path=save_path, pretty=pretty, quiet=quiet)
        self.forwarder = Forwarder(
            forward_url=forward_url,
            forward_retries=forward_retries,
            forward_concurrency=forward_concurrency,
            quiet=quiet
        ) if forward_url else None
        self.coordinator = EventCoordinator(self.logger, self.forwarder)
        self._started = False
    
    async def log(self, event: Dict[str, Any]) -> None:
        """Log a webhook event (legacy interface)."""
        if not self._started and self.forwarder:
            await self.coordinator.start()
            self._started = True
        
        await self.coordinator.handle_event(event)
    
    async def close(self) -> None:
        """Close resources (legacy interface)."""
        await self.coordinator.stop()