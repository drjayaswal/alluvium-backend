from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

get_settings = settings()

engine = create_engine(
    get_settings.DATABASE_URL,
    pool_size=10, 
    max_overflow=20, 
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"}
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
