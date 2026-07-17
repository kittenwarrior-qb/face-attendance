"""Application configuration loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "Face Attendance API"
    log_level: str = "INFO"

    # --- InsightFace ---
    insightface_model_pack: str = "buffalo_l"
    insightface_det_size: int = 640
    insightface_ctx_id: int = -1  # -1 = CPU, >=0 = GPU device id
    face_match_threshold: float = 0.5

    # --- Storage ---
    # No local database - embeddings and photos are stored directly in Odoo
    # (see OdooService). This only controls whether the registration photo is
    # also pushed to the employee's Odoo photo field.
    store_original_image: bool = True

    # --- Security ---
    # Required as a X-API-Key header on POST /register. Leave empty only for local dev -
    # if unset, /register is open to anyone who can reach this service.
    register_api_key: str = ""

    # Comma-separated list of origins allowed to call this API from browser JS
    # (e.g. the Odoo domain embedding the face-capture widget). Empty = no
    # cross-origin browser access, only same-origin (the bundled kiosk UI) works.
    cors_allowed_origins: str = ""

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # --- Liveness (anti-spoofing) ---
    # off     = skip the check entirely.
    # warn    = run it and log the score, but never block (use this first to
    #           calibrate the threshold against real employees/cameras).
    # enforce = reject verification when the face scores below the threshold.
    liveness_mode: str = "off"
    # Minimum mean "real" probability (0..1) from the MiniFASNet ensemble.
    liveness_threshold: float = 0.5
    # Override the bundled model directory (app/models_data) if needed.
    liveness_model_dir: str = ""

    @property
    def liveness_active(self) -> bool:
        return self.liveness_mode in ("warn", "enforce")

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
