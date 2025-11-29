"""fasthook - A high-performance local webhook receiver and relay tool.

OPTIMIZED & PRODUCTION-READY v2.0.0

Features:
- High-performance async webhook receiving
- Configurable request forwarding with retry logic
- Event recording and replay capabilities
- Mock server with scripted responses
- Real-time and offline testing support

Author: Jermy Pena
License: MIT
"""

__version__ = "2.0.0"
__author__ = "Jermy Pena"
__license__ = "MIT"

# Public API
from .logger import Logger, Forwarder, EventCoordinator, EventLogger
from .server import create_app
from .mock import MockServer
from .replay import EventReplayer
from .utils import get_timestamp, safe_parse_json, safe_decode_body, pretty_print

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__license__",
    
    # Core components
    "Logger",
    "Forwarder",
    "EventCoordinator",
    "EventLogger",
    "create_app",
    "MockServer",
    "EventReplayer",
    
    # Utilities
    "get_timestamp",
    "safe_parse_json",
    "safe_decode_body",
    "pretty_print",
]