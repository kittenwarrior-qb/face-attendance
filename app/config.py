"""Application configuration loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "Face Attendance API"
    log_level: str = "INFO"

    # --- Database ---
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/face_attendance"

    # --- InsightFace ---
    insightface_model_pack: str = "buffalo_l"
    insightface_det_size: int = 640
    insightface_ctx_id: int = -1  # -1 = CPU, >=0 = GPU device id
    face_match_threshold: float = 0.5

    # --- Image storage ---
    store_original_image: bool = True
    image_storage_dir: str = "/app/storage/faces"

    # --- Security ---
    # Required as a X-API-Key header on POST /register. Leave empty only for local dev -
    # if unset, /register is open to anyone who can reach this service.
    register_api_key: str = ""

    # --- Odoo ---
    odoo_url: str = "http://localhost:8069"
    odoo_db: str = "odoo"
    odoo_username: str = "admin"
    odoo_password: str = "admin"
    odoo_attach_image: bool = False
    odoo_timeout: int = 10

    @property
    def insightface_det_size_tuple(self) -> tuple[int, int]:
        return (self.insightface_det_size, self.insightface_det_size)


@lru_cache
def get_settings() -> Settings:
    return Settings()
