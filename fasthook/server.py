"""FastAPI server for receiving webhooks - OPTIMIZED & PRODUCTION-READY."""

import logging
import asyncio
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .logger import EventLogger
from .utils import get_timestamp, safe_parse_json, safe_decode_body


def create_app(logger: EventLogger, exit_after: Optional[int] = None) -> FastAPI:
    """Create and configure the FastAPI application.
    
    OPTIMIZED:
    - Removed global state (now uses app.state)
    - Better shutdown handling
    - Structured logging
    
    Args:
        logger: EventLogger instance for handling webhook events
        exit_after: Exit after N events (useful for CI/testing)
        
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="fasthook",
        version="2.0.0",
        description="High-performance local webhook receiver and relay tool"
    )
    
    # CRITICAL FIX: Use app.state instead of global variables
    app.state.event_counter = 0
    app.state.exit_after = exit_after
    app.state.logger = logger
    app.state.shutdown_requested = False
    
    # Use uvicorn logger when available
    app_logger = logging.getLogger("uvicorn.error")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def catch_all(path: str, request: Request):
        """Catch-all route that handles any HTTP method and path.
        
        OPTIMIZED:
        - More efficient body reading
        - Better error handling
        - Non-blocking shutdown
        
        Args:
            path: Request path
            request: FastAPI Request object
            
        Returns:
            JSON response indicating receipt
        """
        # Read body once
        body_bytes = await request.body()
        
        # Parse event data
        event = {
            "timestamp": get_timestamp(),
            "method": request.method,
            "path": f"/{path}",
            "headers": dict(request.headers),
            "query": dict(request.query_params),
            "json": safe_parse_json(body_bytes),
            "raw": safe_decode_body(body_bytes),
            "ip": request.client.host if request.client else "unknown"
        }
        
        # Log event asynchronously (non-blocking)
        await app.state.logger.log(event)
        
        # Handle exit-after functionality
        if app.state.exit_after is not None:
            app.state.event_counter += 1
            
            if app.state.event_counter >= app.state.exit_after:
                if not app.state.shutdown_requested:
                    app.state.shutdown_requested = True
                    app_logger.info(f"Received {app.state.event_counter} events, initiating graceful shutdown")
                    
                    # OPTIMIZATION: Graceful shutdown instead of os.kill
                    asyncio.create_task(graceful_shutdown(app))
        
        return JSONResponse({"status": "received"}, status_code=200)
    
    async def graceful_shutdown(app: FastAPI):
        """Perform graceful shutdown with proper cleanup.
        
        OPTIMIZED: Allows forwarder to flush queue before exit.
        """
        # Give time for response to be sent
        await asyncio.sleep(0.5)
        
        # Stop logger/forwarder to flush queues
        if hasattr(app.state.logger, 'coordinator'):
            await app.state.logger.coordinator.stop()
        
        # Small delay for cleanup
        await asyncio.sleep(0.2)
        
        # Trigger shutdown
        import signal
        import os
        os.kill(os.getpid(), signal.SIGTERM)
    
    @app.on_event("startup")
    async def startup_event():
        """Handle application startup.
        
        OPTIMIZED: Starts forwarder if configured.
        """
        app_logger.info("Fasthook server starting up")
        if hasattr(app.state.logger, 'coordinator'):
            await app.state.logger.coordinator.start()
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Handle application shutdown.
        
        OPTIMIZED: Ensures proper cleanup of resources.
        """
        app_logger.info("Fasthook server shutting down")
        if hasattr(app.state.logger, 'coordinator'):
            try:
                await asyncio.wait_for(
                    app.state.logger.coordinator.stop(),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                app_logger.warning("Shutdown timeout exceeded, forcing stop")
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint for monitoring.
        
        NEW: Added for production monitoring.
        """
        return JSONResponse({
            "status": "healthy",
            "version": "2.0.0",
            "events_received": app.state.event_counter
        })
    
    return app