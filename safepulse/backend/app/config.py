from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal

class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./safepulse.db"

    # Connection pool settings (used when DATABASE_URL is PostgreSQL)
    DB_POOL_SIZE: int = 20          # concurrent connections per worker
    DB_MAX_OVERFLOW: int = 40       # extra connections under burst load
    DB_POOL_TIMEOUT: int = 30       # seconds to wait for a connection
    DB_POOL_RECYCLE: int = 1800     # recycle connections every 30 min

    # ── Security ──────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-32-char-minimum"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 240   # 4 hours
    FERNET_KEY: str = ""

    # ── Rate limiting ─────────────────────────────────────
    RATE_LIMIT_SOS: str = "10/minute"       # SOS trigger
    RATE_LIMIT_AUTH: str = "20/minute"      # login/register
    RATE_LIMIT_DEFAULT: str = "200/minute"  # all other endpoints

    # ── External services ─────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    TWILIO_SID: str = ""
    TWILIO_TOKEN: str = ""
    TWILIO_PHONE: str = ""
    EMERGENCY_NUMBER: str = "112"
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    RAZORPAY_KEY: str = ""
    RAZORPAY_SECRET: str = ""
    ABHA_BASE_URL: str = "https://dev.abdm.gov.in/gateway"
    GOOGLE_MAPS_API_KEY: str = ""
    APP_BASE_URL: str = "http://localhost:8000"

    # ── App behaviour ─────────────────────────────────────
    ENVIRONMENT: Literal["development", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    WORKERS: int = 1   # set to CPU count in production

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
