from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sky Weaver Hub"
    environment: str = Field(default="development", validation_alias="SKYWEAVER_ENV")
    host: str = Field(default="0.0.0.0", validation_alias="SKYWEAVER_HOST")
    port: int = Field(default=8765, validation_alias="SKYWEAVER_PORT")
    secret_key: str = Field(default="dev-change-me", validation_alias="SKYWEAVER_SECRET_KEY")
    data_dir: Path = Field(default=Path("./data"), validation_alias="SKYWEAVER_DATA_DIR")
    config_dir: Path = Field(default=Path("./config"), validation_alias="SKYWEAVER_CONFIG_DIR")
    log_dir: Path = Field(default=Path("./logs"), validation_alias="SKYWEAVER_LOG_DIR")
    database_path: Path | None = Field(default=None, validation_alias="SKYWEAVER_DB")
    cors_origins: str = Field(default="http://localhost:8080,http://127.0.0.1:8080")
    admin_username: str = Field(default="admin", validation_alias="SKYWEAVER_ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, validation_alias="SKYWEAVER_ADMIN_PASSWORD")
    admin_password_hash: str | None = Field(default=None, validation_alias="SKYWEAVER_ADMIN_PASSWORD_HASH")
    observatory_name: str = Field(default="Sky Weaver Observatory", validation_alias="SKYWEAVER_OBSERVATORY_NAME")
    observatory_latitude: float = Field(default=0, validation_alias="SKYWEAVER_OBSERVATORY_LATITUDE")
    observatory_longitude: float = Field(default=0, validation_alias="SKYWEAVER_OBSERVATORY_LONGITUDE")
    observatory_timezone: str = Field(default="UTC", validation_alias="SKYWEAVER_OBSERVATORY_TIMEZONE")
    primary_camera_adapter: str = Field(default="mock", validation_alias="SKYWEAVER_PRIMARY_CAMERA_ADAPTER")
    public_page_enabled: bool = Field(default=True, validation_alias="SKYWEAVER_PUBLIC_PAGE_ENABLED")
    first_setup_required: bool = Field(default=True, validation_alias="SKYWEAVER_FIRST_SETUP_REQUIRED")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def db_path(self) -> Path:
        return self.database_path or self.data_dir / "skyweaver.db"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def thumbnail_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def product_dir(self) -> Path:
        return self.data_dir / "products"

    def ensure_dirs(self) -> None:
        for path in [self.data_dir, self.config_dir, self.log_dir, self.image_dir, self.thumbnail_dir, self.product_dir]:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
