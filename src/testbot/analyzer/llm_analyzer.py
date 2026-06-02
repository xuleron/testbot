"""LLM 驱动的项目分析增强。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.llm.prompts import ANALYZE_SYSTEM, ANALYZE_USER
from testbot.models.project import ProjectAnalysis
from testbot.utils.project_files import collect_source_files

logger = logging.getLogger(__name__)


class LLMAnalysisInsight(BaseModel):
    summary: str = ""
    core_features: list[str] = Field(default_factory=list)
    test_focus: list[str] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)
    recommended_case_types: list[str] = Field(default_factory=list)


class LLMProjectAnalyzer:
    """在结构扫描基础上，用 LLM 深度理解项目。"""

    def __init__(self, settings: Settings, client: LLMClient | None = None):
        self.settings = settings
        self.client = client or LLMClient(settings)

    def enrich(self, analysis: ProjectAnalysis, project_path: Path) -> ProjectAnalysis:
        files = collect_source_files(
            project_path,
            max_files=self.settings.llm_context_max_files,
            max_chars=self.settings.llm_context_max_chars,
        )
        source_context = self._format_files(files)
        structure_json = json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2)

        messages = [
            {"role": "system", "content": ANALYZE_SYSTEM},
            {
                "role": "user",
                "content": ANALYZE_USER.format(
                    structure_json=structure_json,
                    source_context=source_context,
                ),
            },
        ]

        logger.info("正在调用 LLM 分析项目...")
        raw = self.client.chat(messages, json_mode=True)
        data = self.client.parse_json(raw)
        insight = LLMAnalysisInsight.model_validate(data)

        merged_summary = insight.summary
        if analysis.readme_summary and insight.summary:
            merged_summary = f"{insight.summary}\n\nREADME 摘要: {analysis.readme_summary[:500]}"
        elif analysis.readme_summary:
            merged_summary = analysis.readme_summary

        return analysis.model_copy(
            update={
                "readme_summary": merged_summary,
                "llm_summary": insight.summary,
                "core_features": insight.core_features,
                "test_focus": insight.test_focus,
                "risk_areas": insight.risk_areas,
                "recommended_case_types": insight.recommended_case_types,
            }
        )

    @staticmethod
    def _format_files(files: list[tuple[str, str]]) -> str:
        parts = []
        for rel, content in files:
            parts.append(f"### {rel}\n```\n{content}\n```")
        return "\n\n".join(parts) if parts else "(无可用源码)"
