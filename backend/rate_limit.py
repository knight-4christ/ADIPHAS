from slowapi import Limiter  # type: ignore[import-untyped]
from slowapi.util import get_remote_address  # type: ignore[import-untyped]

# Rate limiter instance using in-memory storage (suitable for SQLite setup)
# gets the client IP address using get_remote_address
limiter = Limiter(key_func=get_remote_address)
