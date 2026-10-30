from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VeriSonar"
    app_env: str = "development"
    app_debug: bool = False
    secret_key: str = "cambiar-esta-clave-en-produccion"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    default_locale: str = "es"
    supported_locales: str = "es,en"
    processing_mode: Literal["offline", "online"] = "offline"

    postgres_user: str = "verisonar"
    postgres_password: str = "verisonar"
    postgres_db: str = "verisonar"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str | None = None

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    upload_dir: str = "/data/uploads"
    report_dir: str = "/data/reports"
    model_dir: str = "/data/models"

    enable_vosk: bool = True
    enable_whisper: bool = True
    whisper_model_size: str = "large-v3"
    vosk_model_name: str = "vosk-model-small-es-0.42"

    enable_transformers: bool = False
    nlp_model_path: str = "/data/models/nlp"
    enable_praat: bool = True

    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://frontend:3000"

    prometheus_enabled: bool = True
    log_level: str = "INFO"

    push_enabled: bool = False
    fcm_server_key: str = ""

    bootstrap_admin_email: str = "admin@verisonar.local"
    bootstrap_admin_password: str = "VeriSonar.Admin1"
    bootstrap_admin_name: str = "Administrador VeriSonar"

    @computed_field
    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def locale_list(self) -> list[str]:
        return [item.strip() for item in self.supported_locales.split(",") if item.strip()]

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @computed_field
    @property
    def is_offline(self) -> bool:
        return self.processing_mode == "offline"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
