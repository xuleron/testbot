from pydantic import BaseModel, Field


class ProjectModule(BaseModel):
    name: str
    path: str
    kind: str = Field(description="模块类型，如 package / api / service / test")
    summary: str = ""


class ProjectAnalysis(BaseModel):
    """被测项目分析结果。"""

    project_path: str
    project_name: str
    language: str = "unknown"
    framework: str = ""
    test_framework: str = ""
    readme_summary: str = ""
    modules: list[ProjectModule] = Field(default_factory=list)
    existing_tests: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    # LLM 增强字段
    llm_summary: str = ""
    core_features: list[str] = Field(default_factory=list)
    test_focus: list[str] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)
    recommended_case_types: list[str] = Field(default_factory=list)
