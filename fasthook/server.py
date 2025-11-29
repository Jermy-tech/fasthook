"""FastAPI server for receiving webhooks."""

from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .logger import EventLogger
from .utils import get_timestamp, safe_parse_json, safe_decode_body


def create_app(logger: EventLogger) -> FastAPI:
    """Create and configure the FastAPI application.
    
    Args:
        logger: EventLogger instance for handling webhook events
        
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(title="fasthook", version="1.0.0")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def catch_all(path: str, request: Request):
        """Catch-all route that handles any HTTP method and path.
        
        Args:
            path: Request path
            request: FastAPI Request object
            
        Returns:
            JSON response indicating receipt
        """
        body_bytes = await request.body()
        
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
        
        await logger.log(event)
        
        return JSONResponse({"status": "received"}, status_code=200)
    
    return app
