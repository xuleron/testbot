from datetime import datetime

from pydantic import BaseModel, Field

from testbot.models.testcase import StepResult, TestStepResult


class CaseExecutionResult(BaseModel):
    case_id: int | None = None
    title: str
    status: StepResult
    steps: list[TestStepResult] = Field(default_factory=list)
    duration_ms: int = 0
    error: str = ""
    automated: bool = False
    bug_id: int | None = None


class ExecutionReport(BaseModel):
    project_path: str
    started_at: datetime
    finished_at: datetime | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    bugs_filed: int = 0
    results: list[CaseExecutionResult] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.passed / self.total * 100, 2)
