from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    frontend_url: str
    
    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def settings():
    return Settings()
