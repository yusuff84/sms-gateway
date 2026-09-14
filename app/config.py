from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    PROJECT_NAME: str = "SMS Gateway API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "sms-gateway-secret-key-change-me-in-production-9988"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./sms_gateway.db"
    
    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Device Settings
    DEVICE_OFFLINE_THRESHOLD_SECONDS: int = 60

    # Anti-Flood Protection: Minimum interval between sending to the same phone number
    PHONE_NUMBER_COOLDOWN_SECONDS: int = 45

    # Balance Protection: Strictly allow only Russian mobile numbers (+79XXXXXXXXX)
    ONLY_RU_MOBILE: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
