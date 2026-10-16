from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://neondb_owner:npg_4gNAKOoDIt0y@ep-lingering-thunder-b5clr251-pooler.c-7.us-east-2.aws.neon.tech/agro_services_prod?sslmode=require&channel_binding=require"
    jwt_secret: str = "development-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin123"


settings = Settings()