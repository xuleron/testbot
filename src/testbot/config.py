from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from testbot.models.testcase import CaseType


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 禅道
    zentao_url: str = Field(default="https://zentao.example.com", alias="ZENTAO_URL")
    zentao_base_path: str = Field(default="", alias="ZENTAO_BASE_PATH")
    zentao_account: str = Field(default="admin", alias="ZENTAO_ACCOUNT")
    zentao_password: str = Field(default="", alias="ZENTAO_PASSWORD")
    zentao_product_id: int = Field(
        default=0,
        alias="ZENTAO_PRODUCT_ID",
        description="产品 ID，0 表示从项目自动解析",
    )
    zentao_project_id: int = Field(default=0, alias="ZENTAO_PROJECT_ID")
    zentao_execution_id: int = Field(
        default=0,
        alias="ZENTAO_EXECUTION_ID",
        description="迭代 ID，可选，默认不关联",
    )
    zentao_module_id: int = Field(default=0, alias="ZENTAO_MODULE_ID")
    zentao_testtask_id: int = Field(default=0, alias="ZENTAO_TESTTASK_ID")
    zentao_auto_create_modules: bool = Field(default=True, alias="ZENTAO_AUTO_CREATE_MODULES")
    zentao_auto_create_bugs: bool = Field(
        default=True,
        alias="ZENTAO_AUTO_CREATE_BUGS",
        description="测试失败时自动在禅道提 Bug",
    )
    zentao_bug_type: str = Field(default="codeerror", alias="ZENTAO_BUG_TYPE")
    zentao_bug_severity: int = Field(default=3, alias="ZENTAO_BUG_SEVERITY")
    zentao_bug_pri: int = Field(default=3, alias="ZENTAO_BUG_PRI")
    zentao_opened_build: str = Field(default="trunk", alias="ZENTAO_OPENED_BUILD")
    zentao_bug_on_blocked: bool = Field(default=False, alias="ZENTAO_BUG_ON_BLOCKED")
    zentao_auth_mode: str = Field(
        default="auto",
        alias="ZENTAO_AUTH_MODE",
        description="禅道认证: auto | session | rest（12.x 请用 auto 或 session）",
    )
    zentao_app_code: str = Field(default="", alias="ZENTAO_APP_CODE")
    zentao_app_secret: str = Field(default="", alias="ZENTAO_APP_SECRET")

    # 被测项目
    target_project_path: str = Field(default=".", alias="TARGET_PROJECT_PATH")
    target_app_url: str = Field(
        default="",
        alias="TARGET_APP_URL",
        description="被测应用访问地址",
    )
    target_app_login_url: str = Field(
        default="",
        alias="TARGET_APP_LOGIN_URL",
        description="登录页地址，留空则使用 TARGET_APP_URL",
    )
    target_app_username: str = Field(default="", alias="TARGET_APP_USERNAME")
    target_app_password: str = Field(default="", alias="TARGET_APP_PASSWORD")

    # Playwright 浏览器
    browser_headless: bool = Field(default=False, alias="BROWSER_HEADLESS")
    browser_timeout_ms: int = Field(default=30000, alias="BROWSER_TIMEOUT_MS")
    browser_slow_mo: int = Field(default=0, alias="BROWSER_SLOW_MO")
    browser_viewport_width: int = Field(default=1280, alias="BROWSER_VIEWPORT_WIDTH")
    browser_viewport_height: int = Field(default=720, alias="BROWSER_VIEWPORT_HEIGHT")
    browser_username_selector: str = Field(default="", alias="BROWSER_USERNAME_SELECTOR")
    browser_password_selector: str = Field(default="", alias="BROWSER_PASSWORD_SELECTOR")
    browser_submit_selector: str = Field(default="", alias="BROWSER_SUBMIT_SELECTOR")

    # 测试执行
    executor_mode: str = Field(
        default="auto",
        alias="EXECUTOR_MODE",
        description="执行模式: auto | llm | framework | playwright",
    )
    llm_exec_batch_size: int = Field(default=10, alias="LLM_EXEC_BATCH_SIZE")
    llm_exec_max_cases: int = Field(
        default=0,
        alias="LLM_EXEC_MAX_CASES",
        description="LLM 执行用例上限，0 表示不限制",
    )

    # TestBot
    report_output_dir: str = Field(default=".reports", alias="REPORT_OUTPUT_DIR")
    default_case_priority: int = Field(default=3, alias="DEFAULT_CASE_PRIORITY")
    default_case_type: CaseType = Field(default=CaseType.FEATURE, alias="DEFAULT_CASE_TYPE")
    planner_mode: str = Field(default="llm", alias="PLANNER_MODE")

    # LLM（OpenAI 兼容 API）
    llm_api_base: str = Field(default="https://api.openai.com/v1", alias="LLM_API_BASE")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_provider: str = Field(
        default="openai",
        alias="LLM_PROVIDER",
        description="LLM 服务商: openai | deepseek | ollama",
    )
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    llm_timeout: int = Field(default=120, alias="LLM_TIMEOUT")
    llm_context_max_files: int = Field(default=30, alias="LLM_CONTEXT_MAX_FILES")
    llm_context_max_chars: int = Field(default=80000, alias="LLM_CONTEXT_MAX_CHARS")
    llm_min_cases: int = Field(default=5, alias="LLM_MIN_CASES")
    llm_max_cases: int = Field(default=20, alias="LLM_MAX_CASES")
    llm_cases_per_feature: int = Field(
        default=3,
        alias="LLM_CASES_PER_FEATURE",
        description="全量模式下每个功能点至少生成的用例数",
    )
    llm_feature_batch_size: int = Field(
        default=5,
        alias="LLM_FEATURE_BATCH_SIZE",
        description="全量模式下每批处理的功能点数量",
    )
    llm_inventory_max_files: int = Field(default=100, alias="LLM_INVENTORY_MAX_FILES")
    llm_inventory_max_chars: int = Field(default=150000, alias="LLM_INVENTORY_MAX_CHARS")
    llm_inventory_chunk_files: int = Field(
        default=25,
        alias="LLM_INVENTORY_CHUNK_FILES",
        description="功能点盘点时每批扫描的文件数，避免单次 JSON 过长",
    )
    llm_inventory_max_tokens: int = Field(
        default=8192,
        alias="LLM_INVENTORY_MAX_TOKENS",
        description="功能点盘点单次 LLM 回复 token 上限",
    )
    use_llm_analyze: bool = Field(default=True, alias="USE_LLM_ANALYZE")

    @property
    def zentao_api_base(self) -> str:
        base = self.zentao_url.rstrip("/")
        if self.zentao_base_path:
            return f"{base}/{self.zentao_base_path.strip('/')}"
        return base

    def resolve_target_path(self, override: str | None = None) -> Path:
        path = Path(override or self.target_project_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    def ensure_report_dir(self) -> Path:
        report_dir = Path(self.report_output_dir)
        if not report_dir.is_absolute():
            report_dir = Path.cwd() / report_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir


@lru_cache
def get_settings() -> Settings:
    return Settings()
