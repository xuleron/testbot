"""LLM Prompt 模板。"""

ANALYZE_SYSTEM = """你是一名资深测试架构师。请阅读被测项目的结构与源码片段，输出 JSON。
要求：
1. 准确理解项目用途、核心模块、技术栈
2. 识别关键业务流程与 API/接口
3. 指出测试应重点覆盖的区域与风险点
4. 只输出 JSON，不要 markdown 说明"""

ANALYZE_USER = """请分析以下项目：

## 结构扫描结果
{structure_json}

## 源码与配置
{source_context}

请输出 JSON，格式如下：
{{
  "summary": "项目整体说明（200字以内）",
  "core_features": ["核心功能1", "核心功能2"],
  "test_focus": ["应重点测试的区域"],
  "risk_areas": ["潜在风险点"],
  "recommended_case_types": ["feature", "interface", "unit"]
}}"""

PLAN_SYSTEM = """你是一名资深测试工程师。请基于项目分析结果与源码，设计测试用例并输出 JSON。
要求：
1. 用例应具体、可执行，步骤与预期一一对应
2. 覆盖正常流程、边界条件、异常场景
3. 标题简洁明确，避免空泛描述
4. type 只能是: feature, interface, unit, config, install, performance, security, other（不要用 component、ui、api 等其它值）
5. pri 为 1-4（1 最高）
6. 只输出 JSON，不要 markdown 说明"""

PLAN_USER = """请为以下项目设计测试用例：

## 项目分析
{analysis_json}

## 源码与配置
{source_context}

请输出 JSON，格式如下：
{{
  "cases": [
    {{
      "title": "用例标题",
      "type": "feature",
      "pri": 3,
      "precondition": "前置条件",
      "source": "关联模块或文件",
      "module_name": "系统模块名（如 user、order、api）",
      "steps": [
        {{"action": "操作步骤", "expect": "预期结果"}}
      ]
    }}
  ]
}}

请生成 {min_cases} 到 {max_cases} 条高质量用例。"""

INVENTORY_SYSTEM = """你是一名资深测试架构师。请全面阅读项目结构与源码，列出所有可测试的功能点。
要求：
1. 覆盖页面、菜单、业务流程、API 接口、表单、权限、配置等用户可见或可调用功能
2. 不要遗漏模块；同一模块下的子功能也要分别列出
3. 每个功能点需关联源码路径或模块名
4. 只输出 JSON，不要 markdown 说明"""

INVENTORY_USER = """请为以下项目列出全部功能点：

## 项目分析
{analysis_json}

## 源码与配置
{source_context}

请输出 JSON，格式如下：
{{
  "features": [
    {{
      "name": "功能名称（如：用户登录）",
      "module": "所属模块（如：auth）",
      "source": "关联文件或目录路径",
      "description": "功能简述",
      "scenarios": ["正常流程", "边界条件", "异常场景"]
    }}
  ]
}}

请尽可能完整地列出所有功能点，不要只挑重点。"""

INVENTORY_CHUNK_USER = """请为以下项目片段列出涉及的全部功能点（本批仅为项目一部分源码）：

## 项目分析
{analysis_json}

## 本批源码（第 {chunk_no}/{chunk_total} 批）
{source_context}

请输出 JSON，格式如下：
{{
  "features": [
    {{
      "name": "功能名称",
      "module": "所属模块",
      "source": "关联文件或目录路径",
      "description": "功能简述",
      "scenarios": ["正常流程", "边界条件", "异常场景"]
    }}
  ]
}}

只列出本批源码中实际出现的功能点，不要重复输出与源码无关的猜测。"""

FEATURE_PLAN_SYSTEM = """你是一名资深测试工程师。请为指定的功能点设计测试用例并输出 JSON。
要求：
1. 每个功能点至少生成 {cases_per_feature} 条用例，覆盖正常、边界、异常场景
2. 用例应具体、可执行，步骤与预期一一对应
3. title 中建议包含功能点名称前缀，便于识别
4. type 只能是: feature, interface, unit, config, install, performance, security, other（不要用 component、ui、api 等其它值）
5. pri 为 1-4（1 最高）
6. 只输出 JSON，不要 markdown 说明"""

FEATURE_PLAN_USER = """请为以下功能点设计测试用例：

## 项目分析（摘要）
{analysis_summary}

## 本批功能点
{features_json}

## 相关源码
{source_context}

请输出 JSON，格式如下：
{{
  "cases": [
    {{
      "title": "用例标题",
      "type": "feature",
      "pri": 3,
      "precondition": "前置条件",
      "source": "关联模块或文件",
      "module_name": "系统模块名",
      "steps": [
        {{"action": "操作步骤", "expect": "预期结果"}}
      ]
    }}
  ]
}}

本批共 {feature_count} 个功能点，请合计生成至少 {min_cases} 条用例。"""

BROWSER_STEP_SYSTEM = """你是浏览器自动化测试工程师。根据当前页面状态与测试步骤，生成 Playwright 操作序列（JSON）。
允许的操作 type:
- click: 点击元素（selector 必填）
- fill: 输入文本（selector + value）
- press: 按键（selector + value，如 Enter）
- goto: 跳转 URL（value 填完整 URL）
- wait: 等待毫秒（value 填数字）
- wait_for_selector: 等待元素（selector）
- expect_text: 断言页面包含文本（value 填期望文字）
- expect_url: 断言 URL（value 填 URL 片段）
- select: 下拉选择（selector + value）

selector 优先使用稳定选择器: data-testid、#id、name、[placeholder]、text=按钮文字。
只输出 JSON，不要 markdown。"""

BROWSER_STEP_USER = """项目: {project_name}
用例: {case_title}
前置: {precondition}

## 当前步骤
操作: {step_action}
预期: {step_expect}

## 当前页面
URL: {page_url}
标题: {page_title}
可见文本（摘要）:
{page_text}

请输出 JSON:
{{
  "actions": [
    {{"type": "click", "selector": "text=提交", "value": ""}}
  ],
  "note": "操作说明"
}}

若无需操作仅做断言，可只返回 expect_text。"""

EXECUTE_SYSTEM = """你是一名资深测试工程师，正在自动执行测试用例。
请根据源码、项目分析与测试输出，判定每条用例的执行结果。
要求：
1. 基于代码逻辑、接口定义、现有自动化测试输出进行客观判定
2. status 只能是: pass, fail, blocked, n/a
   - pass: 从代码/测试证据看功能已实现且符合预期
   - fail: 明显缺失实现、逻辑错误或测试输出显示失败
   - blocked: 依赖外部环境/数据/权限，无法从现有信息判定
   - n/a: 纯 UI 交互且无任何可验证依据（尽量少用）
3. real 字段需简要说明判定依据（引用文件/函数/测试输出）
4. 每条用例返回逐步骤结果 steps（与用例步骤数量一致）
5. 只输出 JSON，不要 markdown 说明"""

EXECUTE_USER = """请执行以下测试用例并给出结果（批次 {batch_no}/{batch_total}）：

## 项目分析
{analysis_summary}
{app_section}{framework_section}
## 待执行用例
{cases_json}

## 相关源码
{source_context}

请输出 JSON：
{{
  "results": [
    {{
      "title": "用例标题（与输入一致）",
      "status": "pass",
      "real": "判定依据摘要",
      "steps": [
        {{"result": "pass", "real": "步骤实际结果说明"}}
      ]
    }}
  ]
}}

必须为每条输入用例都给出结果。"""
