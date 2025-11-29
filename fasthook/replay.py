"""Event replay functionality - OPTIMIZED & PRODUCTION-READY."""

import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
import httpx


class EventReplayer:
    """Replays saved webhook events with configurable timing.
    
    OPTIMIZED:
    - Rate limiting to prevent overwhelming targets
    - Better error handling
    - Resource cleanup
    - Progress reporting
    """
    
    # NEW: Add rate limiting
    DEFAULT_MAX_RPS = 100  # Maximum requests per second
    
    def __init__(
        self,
        events_file: Path,
        rate: float = 1.0,
        target_url: Optional[str] = None,
        fixed_delay: float = 0.0,
        replay_once: bool = False,
        max_rps: Optional[float] = None
    ):
        """Initialize the EventReplayer.
        
        OPTIMIZED: Added max_rps for rate limiting.
        
        Args:
            events_file: Path to newline-delimited JSON events file
            rate: Playback rate multiplier (1.0 = real-time, 2.0 = 2x speed)
            target_url: Target URL to replay events to (if None, just prints)
            fixed_delay: Fixed delay between events (overrides timing if > 0)
            replay_once: Replay events once preserving original timing
            max_rps: Maximum requests per second (default: 100)
        """
        self.events_file = events_file
        self.rate = rate
        self.target_url = target_url
        self.fixed_delay = fixed_delay
        self.replay_once = replay_once
        self.max_rps = max_rps or self.DEFAULT_MAX_RPS
        self.logger = logging.getLogger("fasthook.replay")
        self._http_client: Optional[httpx.AsyncClient] = None
        self._last_request_time: Optional[float] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client.
        
        OPTIMIZED: Added connection pooling.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0
                )
            )
        return self._http_client
    
    async def replay(self) -> None:
        """Replay all events from the file.
        
        OPTIMIZED: Better resource cleanup and error handling.
        """
        events = self._load_events()
        
        if not events:
            self.logger.warning("No events found to replay")
            return
        
        self.logger.info(f"Replaying {len(events)} events")
        
        try:
            await self._replay_events(events)
        except Exception as e:
            self.logger.error(f"Error during replay: {e}")
            raise
        finally:
            if self._http_client:
                await self._http_client.aclose()
    
    def _load_events(self) -> List[Dict[str, Any]]:
        """Load events from the NDJSON file.
        
        OPTIMIZED: Better error messages.
        
        Returns:
            List of event dictionaries
        """
        events = []
        
        try:
            with open(self.events_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError as e:
                        self.logger.warning(
                            f"Skipping invalid JSON on line {line_num}: {e}\n"
                            f"Content: {line[:100]}"
                        )
        except FileNotFoundError:
            self.logger.error(f"Events file not found: {self.events_file}")
            raise
        except Exception as e:
            self.logger.error(f"Error reading events file: {e}")
            raise
        
        return events
    
    async def _replay_events(self, events: List[Dict[str, Any]]) -> None:
        """Replay events with timing control.
        
        OPTIMIZED: Added rate limiting and progress reporting.
        
        Args:
            events: List of event dictionaries
        """
        total = len(events)
        
        if self.fixed_delay > 0:
            # Fixed delay mode
            for i, event in enumerate(events, 1):
                await self._replay_event(event, i, total)
                
                if i < total:
                    # Apply rate limiting
                    await self._apply_rate_limit()
                    await asyncio.sleep(self.fixed_delay)
        
        elif self.replay_once:
            # Preserve original timing
            start_time = None
            
            for i, event in enumerate(events, 1):
                event_time = self._parse_timestamp(event.get('timestamp'))
                
                if start_time is None:
                    start_time = event_time
                    await self._replay_event(event, i, total)
                else:
                    # Calculate delay from previous event
                    delay = (event_time - start_time).total_seconds() / self.rate
                    if delay > 0:
                        await asyncio.sleep(delay)
                    
                    await self._apply_rate_limit()
                    await self._replay_event(event, i, total)
                    start_time = event_time
        
        else:
            # No delay, replay as fast as possible (with rate limiting)
            for i, event in enumerate(events, 1):
                await self._apply_rate_limit()
                await self._replay_event(event, i, total)
        
        # Print completion message
        print(f"\n✅ Replay complete: {total} events processed")
    
    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting to prevent overwhelming the target.
        
        NEW: Prevents sending requests too fast.
        """
        if self._last_request_time is not None and self.max_rps > 0:
            min_interval = 1.0 / self.max_rps
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
        
        self._last_request_time = asyncio.get_event_loop().time()
    
    def _parse_timestamp(self, timestamp: str) -> datetime:
        """Parse ISO 8601 timestamp.
        
        Args:
            timestamp: ISO 8601 formatted timestamp
            
        Returns:
            datetime object
        """
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    
    async def _replay_event(self, event: Dict[str, Any], index: int, total: int) -> None:
        """Replay a single event.
        
        OPTIMIZED: Better progress reporting.
        
        Args:
            event: Event dictionary
            index: Current event index (1-based)
            total: Total number of events
        """
        # Progress indicator every 10%
        if index == 1 or index == total or index % max(1, total // 10) == 0:
            progress = (index / total) * 100
            print(f"[{index}/{total}] ({progress:.0f}%) Replaying: {event['method']} {event['path']}")
        
        if self.target_url:
            await self._send_event(event)
        else:
            # Just print the event (quiet mode)
            if index <= 5 or index == total:  # Show first 5 and last
                print(f"  Timestamp: {event['timestamp']}")
                if event.get('json'):
                    print(f"  Body: {json.dumps(event['json'])[:100]}...")
    
    async def _send_event(self, event: Dict[str, Any]) -> None:
        """Send an event to the target URL.
        
        OPTIMIZED: Better error handling and retry logic.
        
        Args:
            event: Event dictionary
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                client = await self._get_http_client()
                
                method = event['method']
                path = event['path']
                url = f"{self.target_url.rstrip('/')}{path}"
                
                headers = event['headers'].copy()
                headers.pop('host', None)
                
                body = None
                if event.get('json'):
                    body = json.dumps(event['json'])
                    headers['content-type'] = 'application/json'
                elif event.get('raw'):
                    body = event['raw']
                
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body
                )
                
                # Success - break retry loop
                if response.status_code < 500:
                    return
                
                # Server error - retry
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Server error {response.status_code}, retrying... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Error sending event: {e}, retrying... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(2 ** attempt)
                else:
                    self.logger.error(f"Failed to send event after {max_retries} attempts: {e}")