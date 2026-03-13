from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter instance using in-memory storage (suitable for SQLite setup)
# gets the client IP address using get_remote_address
limiter = Limiter(key_func=get_remote_address)
