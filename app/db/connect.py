from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

get_settings = settings()

engine = create_engine(
    get_settings.DATABASE_URL,
    pool_size=20,  # Increased for better concurrency
    max_overflow=40,  # Increased overflow for traffic spikes
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True,  # Verify connections before using
    pool_timeout=30,  # Timeout for getting connection from pool
    connect_args={"sslmode": "require"},
    echo=False,  # Disable SQL logging in production
    future=True,  # Use SQLAlchemy 2.0 style
)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
