from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── LLM provider switch ───────────────────────────────────────────────────
    # Set exactly ONE of these to true; the rest to false.
    use_azure_openai: bool = Field(False, alias="USE_AZURE_OPENAI")
    use_coxy: bool = Field(False, alias="USE_COXY")          # GitHub Copilot via Coxy proxy
    # If both are false, standard OpenAI is used.

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    azure_openai_api_key: str = Field("", alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str = Field("", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment_name: str = Field("gpt-4o", alias="AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_openai_api_version: str = Field("2024-08-01-preview", alias="AZURE_OPENAI_API_VERSION")

    # ── Standard OpenAI ───────────────────────────────────────────────────────
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", alias="OPENAI_MODEL")

    # ── Coxy (GitHub Copilot proxy) ───────────────────────────────────────────
    coxy_base_url: str = Field("http://localhost:3000/api", alias="COXY_BASE_URL")
    coxy_model: str = Field("gpt-4o", alias="COXY_MODEL")    # any model Copilot supports
    # Coxy uses a dummy API key '_' when a default token is set in its UI.
    coxy_api_key: str = Field("_", alias="COXY_API_KEY")

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    debug: bool = Field(True, alias="DEBUG")

    # ── Paths ─────────────────────────────────────────────────────────────────
    tf_base_path: Path = Field(Path("./terraform"), alias="TF_TEMPLATES_BASE_PATH")

    @property
    def model_name(self) -> str:
        if self.use_coxy:
            return self.coxy_model
        if self.use_azure_openai:
            return self.azure_openai_deployment_name
        return self.openai_model


settings = Settings()
