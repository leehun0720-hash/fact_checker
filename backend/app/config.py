from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    dfc_skill_id: str = ""
    dfc_skill_version: str = "latest"
    claude_model: str = "claude-opus-5"
    max_tokens: int = 32000
    web_search_max_uses: int = 15
    web_fetch_max_uses: int = 10
    pause_turn_max_rounds: int = 12

    # 국가법령정보센터 오픈API 인증값(이메일 아이디). 비우면 법령 도구를 붙이지 않는다.
    law_api_oc: str = ""
    law_tool_max_calls: int = 30

    # 서버 도구 버전 — 최신 web_search/web_fetch는 code_execution_20260120 이상을 요구한다
    code_execution_tool: str = "code_execution_20260521"
    web_search_tool: str = "web_search_20260318"
    web_fetch_tool: str = "web_fetch_20260318"

    # 고객 제공용 인증
    allow_self_signup: bool = False          # 1이면 누구나 새 조직을 만들어 가입 가능. 내부용은 0 + 초대 코드
    default_monthly_job_limit: int = 100     # 새 조직의 월 검증 한도
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    data_dir: Path = Path("./data")
    max_upload_mb: int = 20
    max_concurrent_jobs: int = 2
    mock_verifier: bool = False

    allowed_extensions: tuple[str, ...] = (".pdf", ".docx", ".hwpx", ".md", ".txt")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
