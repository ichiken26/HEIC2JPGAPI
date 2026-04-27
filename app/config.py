from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEIC2JPG_", env_file=".env")

    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    jpeg_quality: int = Field(default=90, ge=1, le=100)
    jpeg_max_output_bytes: int = Field(default=800 * 1024, ge=1)


settings = Settings()
