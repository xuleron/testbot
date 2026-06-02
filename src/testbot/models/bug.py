"""禅道 Bug 模型。"""

from pydantic import BaseModel, Field


class BugDraft(BaseModel):
    title: str
    steps: str = Field(description="重现步骤 / 失败详情")
    product_id: int = 0
    project_id: int = 0
    module_id: int = 0
    case_id: int | None = None
    case_version: int = 1
    type: str = "codeerror"
    severity: int = 3
    pri: int = 3
    opened_build: str = "trunk"
