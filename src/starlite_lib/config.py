"""
All configuration is via environment variables.

Take not of the environment variable prefixes required for each settings class, except
[`AppSettings`][starlite_lib.config.AppSettings].
"""
from pydantic import AnyUrl, BaseSettings, PostgresDsn


# noinspection PyUnresolvedReferences
class AppSettings(BaseSettings):
    """
    Generic application settings. These settings are returned as json by the healthcheck endpoint,
    so do not include any sensitive values here, or if you do ensure to exclude them from
    serialization in the `Config` object.

    Attributes
    ----------
    BUILD_NUMBER : str
        Identity of the CI build of current app instance.
    DEBUG : bool
        If `True` runs `Starlite` in debug mode.
    ENVIRONMENT : str
        "dev", "prod", etc.
    LOG_LEVEL : str
        Stdlib log level names, "DEBUG", "INFO", etc.
    NAME : str
        App name.
    """

    class Config:
        case_sensitive = True

    BUILD_NUMBER: str
    DEBUG: bool
    ENVIRONMENT: str
    LOG_LEVEL: str
    NAME: str

    @property
    def slug(self) -> str:
        """
        A slugified name.

        Returns
        -------
        str
            `self.NAME`, all lowercase and hyphens instead of spaces.
        """
        return "-".join(s.lower() for s in self.NAME.split())


# noinspection PyUnresolvedReferences
class APISettings(BaseSettings):
    """
    API specific configuration.

    Prefix all environment variables with `API_`, e.g., `API_CACHE_EXPIRATION`.

    Attributes
    ----------
    CACHE_EXPIRATION : int
        Default cache key expiration in seconds.
    DEFAULT_PAGINATION_LIMIT : int
        Max records received for collection routes.
    """

    class Config:
        env_prefix = "API_"
        case_sensitive = True

    CACHE_EXPIRATION: int
    DEFAULT_PAGINATION_LIMIT: int
    HEALTH_PATH: str


# noinspection PyUnresolvedReferences
class OpenAPISettings(BaseSettings):
    """
    Configures OpenAPI for the application.

    Prefix all environment variables with `OPENAPI_`, e.g., `OPENAPI_TITLE`.

    Attributes
    ----------
    TITLE : str
        OpenAPI document title.
    VERSION : str
        OpenAPI document version.
    CONTACT_NAME : str
        OpenAPI document contact name.
    CONTACT_EMAIL : str
        OpenAPI document contact email.
    """

    class Config:
        env_prefix = "OPENAPI_"
        case_sensitive = True

    TITLE: str | None
    VERSION: str
    CONTACT_NAME: str
    CONTACT_EMAIL: str


# noinspection PyUnresolvedReferences
class DatabaseSettings(BaseSettings):
    """
    Configures the database for the application.

    Prefix all environment variables with `DB_`, e.g., `DB_URL`.

    Attributes
    ----------
    ECHO : bool
        Enables SQLAlchemy engine logs.
    URL : PostgresDsn
        URL for database connection.
    """

    class Config:
        env_prefix = "DB_"
        case_sensitive = True

    ECHO: bool
    URL: PostgresDsn


# noinspection PyUnresolvedReferences
class CacheSettings(BaseSettings):
    """
    Cache settings for the application.

    Prefix all environment variables with `CACHE_`, e.g., `CACHE_URL`.

    Attributes
    ----------
    URL : AnyUrl
        A redis connection URL.
    """

    class Config:
        env_prefix = "CACHE_"
        case_sensitive = True

    URL: AnyUrl


# noinspection PyUnresolvedReferences
class SentrySettings(BaseSettings):
    """
    Configures sentry for the application.

    Attributes
    ----------
    DSN : str
        The sentry DSN. Set as empty string to disable sentry reporting.
    TRACES_SAMPLE_RATE : float
        % of requests traced by sentry, `0.0` means none, `1.0` means all.
    """

    class Config:
        env_prefix = "SENTRY_"
        case_sensitive = True

    DSN: str
    TRACES_SAMPLE_RATE: float


api_settings = APISettings()
app_settings = AppSettings()
cache_settings = CacheSettings()
db_settings = DatabaseSettings()
openapi_settings = OpenAPISettings()
sentry_settings = SentrySettings()