"""全量功能点覆盖的测试用例生成器。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from pydantic import BaseModel, Field

from testbot.config import Settings
from testbot.llm.client import LLMClient, LLMError
from testbot.llm.prompts import (
    FEATURE_PLAN_SYSTEM,
    FEATURE_PLAN_USER,
    INVENTORY_CHUNK_USER,
    INVENTORY_SYSTEM,
    INVENTORY_USER,
)
from testbot.models.project import ProjectAnalysis
from testbot.models.testcase import TestCaseDraft
from testbot.planner.llm_generator import LLMCasesResponse, LLMTestCaseGenerator
from testbot.utils.project_files import collect_files_for_sources, collect_source_files

logger = logging.getLogger(__name__)


class FeaturePoint(BaseModel):
    name: str
    module: str = ""
    source: str = ""
    description: str = ""
    scenarios: list[str] = Field(default_factory=list)


class FeatureInventory(BaseModel):
    features: list[FeaturePoint]


class FullCoverageGenerator:
    """先盘点全部功能点，再按批生成用例，实现项目级全覆盖。"""

    def __init__(self, settings: Settings, client: LLMClient | None = None):
        self.settings = settings
        self.client = client or LLMClient(settings)
        self._case_builder = LLMTestCaseGenerator(settings, self.client)

    def generate(self, analysis: ProjectAnalysis, project_path: Path | None = None) -> list[TestCaseDraft]:
        path = project_path or Path(analysis.project_path)
        features = self._inventory_features(analysis, path)
        if not features:
            logger.warning("未识别到功能点，回退到常规 LLM 生成")
            return self._case_builder.generate(analysis, path)

        logger.info("已识别 %d 个功能点，开始分批生成用例...", len(features))
        batch_size = max(1, self.settings.llm_feature_batch_size)
        per_feature = max(1, self.settings.llm_cases_per_feature)
        all_cases: list[TestCaseDraft] = []

        for batch_no, start in enumerate(range(0, len(features), batch_size), 1):
            batch = features[start : start + batch_size]
            try:
                batch_cases = self._generate_for_batch(analysis, path, batch, batch_no, per_feature)
            except (ValidationError, LLMError, ValueError) as exc:
                logger.error("批次 %d 生成失败（已跳过，继续下一批）: %s", batch_no, exc)
                continue
            all_cases.extend(batch_cases)
            logger.info(
                "批次 %d/%d: %d 个功能点 → %d 条用例（累计 %d 条）",
                batch_no,
                (len(features) + batch_size - 1) // batch_size,
                len(batch),
                len(batch_cases),
                len(all_cases),
            )

        deduped = self._dedupe_cases(all_cases)
        logger.info("全量覆盖完成: %d 个功能点 → %d 条用例（去重后）", len(features), len(deduped))
        if not deduped:
            logger.warning("全量覆盖未生成任何用例，回退到常规 LLM 生成")
            return self._case_builder.generate(analysis, path)
        return deduped

    def _inventory_features(self, analysis: ProjectAnalysis, path: Path) -> list[FeaturePoint]:
        files = collect_source_files(
            path,
            max_files=self.settings.llm_inventory_max_files,
            max_chars=self.settings.llm_inventory_max_chars,
        )
        if not files:
            return self._merge_with_analysis_modules([], analysis)

        chunk_size = max(1, self.settings.llm_inventory_chunk_files)
        chunks = [files[i : i + chunk_size] for i in range(0, len(files), chunk_size)]
        logger.info(
            "正在分 %d 批盘点功能点（共扫描 %d 个文件，每批 %d 个）...",
            len(chunks),
            len(files),
            chunk_size,
        )

        all_features: list[FeaturePoint] = []
        for chunk_no, chunk_files in enumerate(chunks, 1):
            try:
                batch = self._inventory_file_chunk(analysis, chunk_files, chunk_no, len(chunks))
                all_features.extend(batch)
                logger.info("盘点批次 %d/%d: 识别 %d 个功能点（累计 %d）", chunk_no, len(chunks), len(batch), len(all_features))
            except (ValidationError, LLMError, ValueError) as exc:
                logger.error("盘点批次 %d/%d 失败（已跳过）: %s", chunk_no, len(chunks), exc)

        return self._merge_with_analysis_modules(self._dedupe_features(all_features), analysis)

    def _inventory_file_chunk(
        self,
        analysis: ProjectAnalysis,
        chunk_files: list[tuple[str, str]],
        chunk_no: int,
        chunk_total: int,
    ) -> list[FeaturePoint]:
        source_context = LLMTestCaseGenerator._format_files(chunk_files)
        analysis_json = json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2)
        use_chunk_prompt = chunk_total > 1

        messages = [
            {"role": "system", "content": INVENTORY_SYSTEM},
            {
                "role": "user",
                "content": (
                    INVENTORY_CHUNK_USER.format(
                        analysis_json=analysis_json,
                        source_context=source_context,
                        chunk_no=chunk_no,
                        chunk_total=chunk_total,
                    )
                    if use_chunk_prompt
                    else INVENTORY_USER.format(
                        analysis_json=analysis_json,
                        source_context=source_context,
                    )
                ),
            },
        ]

        raw = self.client.chat(
            messages,
            json_mode=True,
            max_tokens=self.settings.llm_inventory_max_tokens,
        )
        data = self.client.parse_json(raw, array_key="features")
        inventory = FeatureInventory.model_validate(data)
        return [f for f in inventory.features if f.name.strip()]

    def _merge_with_analysis_modules(
        self,
        features: list[FeaturePoint],
        analysis: ProjectAnalysis,
    ) -> list[FeaturePoint]:
        """将结构扫描模块与 LLM 功能点合并，减少遗漏。"""
        seen = {self._feature_key(f) for f in features}
        merged = list(features)

        for mod in analysis.modules:
            key = self._feature_key(FeaturePoint(name=mod.name, source=mod.path))
            if key in seen:
                continue
            merged.append(
                FeaturePoint(
                    name=mod.name,
                    module=mod.name,
                    source=mod.path,
                    description=mod.summary,
                    scenarios=["正常流程", "边界条件", "异常场景"],
                )
            )
            seen.add(key)

        for feat in analysis.core_features:
            key = self._feature_key(FeaturePoint(name=feat))
            if key in seen:
                continue
            merged.append(
                FeaturePoint(
                    name=feat,
                    module=feat.split("-")[0].strip() if "-" in feat else "",
                    description=feat,
                    scenarios=["正常流程", "边界条件", "异常场景"],
                )
            )
            seen.add(key)

        return merged

    def _generate_for_batch(
        self,
        analysis: ProjectAnalysis,
        path: Path,
        batch: list[FeaturePoint],
        batch_no: int,
        cases_per_feature: int,
    ) -> list[TestCaseDraft]:
        source_hints = [f.source for f in batch if f.source] + [f.module for f in batch if f.module]
        files = collect_files_for_sources(
            path,
            source_hints,
            max_files=self.settings.llm_context_max_files,
            max_chars=self.settings.llm_context_max_chars,
        )
        source_context = LLMTestCaseGenerator._format_files(files)
        features_json = json.dumps(
            [f.model_dump() for f in batch],
            ensure_ascii=False,
            indent=2,
        )
        min_cases = len(batch) * cases_per_feature
        analysis_summary = json.dumps(
            {
                "project_name": analysis.project_name,
                "language": analysis.language,
                "framework": analysis.framework,
                "llm_summary": analysis.llm_summary or analysis.readme_summary[:500],
                "test_focus": analysis.test_focus,
            },
            ensure_ascii=False,
            indent=2,
        )

        messages = [
            {
                "role": "system",
                "content": FEATURE_PLAN_SYSTEM.format(cases_per_feature=cases_per_feature),
            },
            {
                "role": "user",
                "content": FEATURE_PLAN_USER.format(
                    analysis_summary=analysis_summary,
                    features_json=features_json,
                    source_context=source_context,
                    feature_count=len(batch),
                    min_cases=min_cases,
                ),
            },
        ]

        logger.info("批次 %d: 正在为 %d 个功能点生成用例...", batch_no, len(batch))
        raw = self.client.chat(messages, json_mode=True, max_tokens=self.settings.llm_max_tokens)
        data = self.client.parse_json(raw, array_key="cases")
        response = LLMCasesResponse.model_validate(data)
        defaults = self._case_builder._base_defaults()
        cases: list[TestCaseDraft] = []
        for item in response.cases:
            cases.append(
                TestCaseDraft(
                    title=item.title,
                    steps=item.steps,
                    precondition=item.precondition,
                    pri=item.pri,
                    type=item.type,
                    source=item.source,
                    module_name=item.module_name or item.source,
                    **defaults,
                )
            )
        return cases

    @staticmethod
    def _dedupe_features(features: list[FeaturePoint]) -> list[FeaturePoint]:
        seen: set[str] = set()
        result: list[FeaturePoint] = []
        for feature in features:
            key = FullCoverageGenerator._feature_key(feature)
            if key in seen:
                continue
            seen.add(key)
            result.append(feature)
        return result

    @staticmethod
    def _feature_key(feature: FeaturePoint) -> str:
        name = feature.name.strip().lower()
        source = feature.source.strip().lower()
        return f"{name}|{source}"

    @staticmethod
    def _dedupe_cases(cases: list[TestCaseDraft]) -> list[TestCaseDraft]:
        seen: set[str] = set()
        result: list[TestCaseDraft] = []
        for case in cases:
            key = case.title.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(case)
        return result
