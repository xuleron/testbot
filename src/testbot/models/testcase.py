from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CaseType(str, Enum):
    FEATURE = "feature"
    INTERFACE = "interface"
    UNIT = "unit"
    CONFIG = "config"
    INSTALL = "install"
    PERFORMANCE = "performance"
    SECURITY = "security"
    OTHER = "other"


# LLM 可能返回的非标准 type，映射到禅道支持的类型
CASE_TYPE_ALIASES: dict[str, CaseType] = {
    "component": CaseType.FEATURE,
    "ui": CaseType.FEATURE,
    "page": CaseType.FEATURE,
    "functional": CaseType.FEATURE,
    "e2e": CaseType.FEATURE,
    "integration": CaseType.FEATURE,
    "web": CaseType.FEATURE,
    "smoke": CaseType.FEATURE,
    "regression": CaseType.FEATURE,
    "api": CaseType.INTERFACE,
    "rest": CaseType.INTERFACE,
    "http": CaseType.INTERFACE,
    "manual": CaseType.OTHER,
    "automation": CaseType.UNIT,
}


def normalize_case_type(value: Any) -> CaseType:
    """将 LLM 返回的 type 规范化为禅道支持的 CaseType。"""
    if isinstance(value, CaseType):
        return value
    if value is None or (isinstance(value, str) and not value.strip()):
        return CaseType.FEATURE
    key = str(value).strip().lower()
    try:
        return CaseType(key)
    except ValueError:
        pass
    if key in CASE_TYPE_ALIASES:
        return CASE_TYPE_ALIASES[key]
    return CaseType.OTHER


class StepResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NA = "n/a"


class TestCaseStep(BaseModel):
    action: str = Field(description="测试步骤")
    expect: str = Field(description="预期结果")


class TestCaseDraft(BaseModel):
    """待写入禅道的测试用例草稿。"""

    title: str
    steps: list[TestCaseStep]
    precondition: str = ""
    pri: int = 3
    type: CaseType = CaseType.FEATURE
    module: int | None = None
    story: int | None = None
    project: int | None = None
    execution: int | None = None
    source: str = Field(default="", description="用例来源说明，如模块/API 名称")
    module_name: str = Field(default="", description="禅道用例模块名，通常对应系统模块")
    zentao_id: int | None = Field(default=None, description="同步到禅道后的 ID")


class TestStepResult(BaseModel):
    result: StepResult
    real: str = Field(description="实际结果描述")
