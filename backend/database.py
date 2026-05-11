from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError
import os
import logging

logger = logging.getLogger(__name__)

# Use environment variable for DB URL.
# For PostgreSQL: DATABASE_URL=postgresql://user:password@host:port/dbname
# Falls back to sqlite for local dev if not set.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/data.db")

# Fix for common Railway/Heroku postgres:// scheme (SQLAlchemy requires postgresql://)
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = "sqlite" in SQLALCHEMY_DATABASE_URL

if is_sqlite:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL with connection pooling hardened for Neon/serverless Postgres.
    # - pool_pre_ping: Detects dead connections before lending them out.
    # - pool_recycle=180: Aggressive recycling for Neon free-tier (drops idle >5min).
    # - connect_args keepalives: Detects broken TCP sooner via OS-level keepalives.
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=180,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI dependency that yields a SQLAlchemy session.

    The finally block is hardened against SSL disconnects from Neon/Render:
    if the underlying connection is already severed, db.close() triggers a
    rollback that raises OperationalError. We catch and discard it because
    the connection is dead anyway — the pool_pre_ping will replace it on
    the next checkout.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except OperationalError:
            # Connection already dead (SSL severed). Nothing to rollback.
            logger.warning("[DB] Session close failed (SSL dropped). Connection discarded by pool.")
        except Exception as e:
            logger.warning(f"[DB] Unexpected error during session close: {e}")
