from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    jwt_secret_key: str
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = False

    redis_url: str

    # Job-queue broker (review F09/F26 migration — see
    # docs/plans/rabbitmq-airflow-migration.md). Default matches
    # docker-compose.yml's rabbitmq service with its dev-only guest/guest
    # creds; override per environment.
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # The in-process APScheduler sweep (expire attempts -> disqualify
    # applications). With more than one web worker/replica this MUST be true on
    # at most one of them, or every process runs the same sweep concurrently.
    # Default off so multi-worker deployments are safe by default; a
    # single-process dev run sets it true in .env. See docs/decisions/D06.
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 15

    # Bootstrap admin (used by `uv run python -m app.scripts.create_admin`).
    # Declared here so setting them in .env actually takes effect —
    # pydantic-settings does not export .env values into os.environ.
    admin_email: str | None = None
    admin_password: str | None = None
    admin_first_name: str = "Admin"
    admin_last_name: str = "User"
    admin_contact_number: str = "N/A"

    # Comma-separated list of allowed CORS origins (e.g. "http://localhost:5173,http://192.168.1.59:5173")
    cors_allow_origins: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings = Settings()
