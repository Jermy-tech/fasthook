"""Mock webhook server with scripted responses - OPTIMIZED & PRODUCTION-READY."""

import json
import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class MockServer:
    """Mock server that responds with scripted responses based on configuration.
    
    OPTIMIZED:
    - Maximum delay limits to prevent DOS
    - Thread-safe call counting
    - Better error handling
    """
    
    # CRITICAL FIX: Maximum delay to prevent hanging
    MAX_DELAY_SECONDS = 30.0
    
    def __init__(self, spec: Dict[str, Any]):
        """Initialize MockServer with a response specification.
        
        Args:
            spec: Response specification dictionary
        """
        self.spec = spec
        self.defaults = spec.get('defaults', {
            'status': 200,
            'delay': 0,
            'body': {'status': 'ok'}
        })
        self.routes = spec.get('routes', {})
        self.logger = logging.getLogger("fasthook.mock")
        self.call_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()  # Thread-safe counter
    
    @classmethod
    def from_file(cls, spec_path: Path) -> 'MockServer':
        """Load MockServer configuration from a file.
        
        OPTIMIZED: Better error messages for invalid files.
        
        Args:
            spec_path: Path to JSON or YAML spec file
            
        Returns:
            MockServer instance
            
        Raises:
            ValueError: If spec file is invalid
        """
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                if spec_path.suffix in ['.yaml', '.yml']:
                    try:
                        import yaml
                        spec = yaml.safe_load(f)
                    except ImportError:
                        raise ImportError(
                            "PyYAML required for YAML specs. Install with: pip install pyyaml"
                        )
                else:
                    spec = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in spec file: {e}")
        except Exception as e:
            raise ValueError(f"Error reading spec file: {e}")
        
        return cls(spec)
    
    def create_app(self) -> FastAPI:
        """Create and configure the FastAPI application for mock server.
        
        OPTIMIZED:
        - Better async handling
        - Thread-safe counters
        - Added health check
        
        Returns:
            Configured FastAPI application
        """
        app = FastAPI(
            title="fasthook-mock",
            version="2.0.0",
            description="Mock webhook server with scripted responses"
        )
        
        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
        async def mock_handler(path: str, request: Request):
            """Handle all requests with configured mock responses.
            
            OPTIMIZED:
            - Thread-safe call counting
            - Delay limits enforced
            - Better error handling
            
            Args:
                path: Request path
                request: FastAPI Request object
                
            Returns:
                Mock response based on configuration
            """
            route_path = f"/{path}"
            method = request.method
            
            # OPTIMIZATION: Thread-safe call counting
            route_key = f"{method} {route_path}"
            async with self._lock:
                self.call_counts[route_key] = self.call_counts.get(route_key, 0) + 1
                call_num = self.call_counts[route_key]
            
            # Find matching route configuration
            response_config = self._get_response_config(route_path, method)
            
            # CRITICAL FIX: Enforce maximum delay
            delay = response_config.get('delay', self.defaults.get('delay', 0))
            delay = min(delay, self.MAX_DELAY_SECONDS)
            
            if delay > 0:
                await asyncio.sleep(delay)
            
            # Get response status and body
            status = response_config.get('status', self.defaults.get('status', 200))
            body = response_config.get('body', self.defaults.get('body', {'status': 'ok'}))
            headers = response_config.get('headers', {})
            
            # Handle sequences (return different responses based on call count)
            if 'sequence' in response_config:
                sequence = response_config['sequence']
                index = min(call_num - 1, len(sequence) - 1)
                seq_config = sequence[index]
                status = seq_config.get('status', status)
                body = seq_config.get('body', body)
                headers = seq_config.get('headers', headers)
            
            self.logger.info(f"{method} {route_path} -> {status} (call #{call_num})")
            
            return JSONResponse(content=body, status_code=status, headers=headers)
        
        @app.get("/__mock__/stats")
        async def mock_stats():
            """Return mock server statistics.
            
            OPTIMIZED: Thread-safe access to stats.
            """
            async with self._lock:
                stats = {
                    'call_counts': dict(self.call_counts),
                    'routes': list(self.routes.keys()),
                    'total_calls': sum(self.call_counts.values())
                }
            return JSONResponse(stats)
        
        @app.post("/__mock__/reset")
        async def mock_reset():
            """Reset mock server statistics.
            
            OPTIMIZED: Thread-safe reset.
            """
            async with self._lock:
                self.call_counts.clear()
            return JSONResponse({'status': 'reset', 'message': 'Call counts cleared'})
        
        @app.get("/__mock__/health")
        async def mock_health():
            """Health check endpoint.
            
            NEW: Added for monitoring.
            """
            return JSONResponse({
                'status': 'healthy',
                'version': '2.0.0',
                'routes_configured': len(self.routes)
            })
        
        return app
    
    def _get_response_config(self, path: str, method: str) -> Dict[str, Any]:
        """Get response configuration for a specific route and method.
        
        OPTIMIZED: Better pattern matching.
        
        Args:
            path: Request path
            method: HTTP method
            
        Returns:
            Response configuration dictionary
        """
        # Exact path match (highest priority)
        if path in self.routes:
            route_config = self.routes[path]
            if isinstance(route_config, dict):
                # Method-specific match
                if method in route_config:
                    return route_config[method]
                # ANY method match
                if 'ANY' in route_config:
                    return route_config['ANY']
        
        # Wildcard matching (prefix matching)
        # Sort by specificity (longest prefix first)
        sorted_routes = sorted(
            [(k, v) for k, v in self.routes.items() if k.endswith('*')],
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        for route_pattern, route_config in sorted_routes:
            prefix = route_pattern[:-1]  # Remove the *
            if path.startswith(prefix):
                if isinstance(route_config, dict):
                    if method in route_config:
                        return route_config[method]
                    if 'ANY' in route_config:
                        return route_config['ANY']
        
        # Return empty config (will use defaults)
        return {}