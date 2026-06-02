# TestBot

自动化测试机器人：**阅读指定项目 → LLM 编写测试用例 → 执行测试 → 汇报结果**，测试用例与执行结果通过**禅道**管理。

> **独立运行**：配置好 LLM API 与禅道后，无需 Cursor 参与，命令行即可完成全流程。

## 标准测试流程

```mermaid
flowchart LR
    A[结构扫描] --> B[LLM 理解项目]
    B --> C[LLM 生成用例]
    C --> D[同步禅道]
    D --> E[执行测试]
    E --> F[回写结果]
```

| 阶段 | 命令 | 说明 |
|------|------|------|
| 1. 分析 | `testbot analyze` | 结构扫描 + **LLM 深度理解** |
| 2. 设计 | `testbot plan` | **LLM 生成**测试用例 |
| 3. 编写 | `testbot sync` | 将用例写入禅道 |
| 4. 执行 | `testbot run` / `testbot execute` | 执行测试（LLM / framework / Playwright） |
| 5. 汇报 | `testbot report` | 本地报告 + 禅道回写 + 自动提 Bug |
| 一键 | `testbot full` | 完整流程 |

## 快速开始

### 1. 安装

```bash
cd TestBot
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e .              # 推荐：安装项目及依赖，并注册 testbot 命令
```

或使用传统方式：

```bash
pip install -r requirements.txt
pip install -e . --no-deps    # 仅注册 testbot 命令行（依赖已手动安装时）
```

开发/测试依赖：

```bash
pip install -r requirements-dev.txt
pip install -e .
```

### 2. 配置

```bash
copy .env.example .env
```

**禅道配置：**

```ini
ZENTAO_URL=https://your-zentao.com
ZENTAO_ACCOUNT=admin
ZENTAO_PASSWORD=your_password
ZENTAO_PROJECT_ID=20              # 可选，记录项目上下文
ZENTAO_PRODUCT_ID=20              # 必填（用例库产品 ID，见 testcase-browse-20 中的数字）
ZENTAO_AUTH_MODE=auto             # 12.x 自动走 Session，无需「创建应用」
ZENTAO_AUTO_CREATE_MODULES=true   # 无模块权限时自动归入根目录
TARGET_PROJECT_PATH=../your-project
```

> **禅道 12.x 说明**：旧版没有「二次开发 → 创建应用」，也不支持 REST API。TestBot 会自动使用 **Session 网页登录**同步用例，只需账号密码和产品 ID，无需 `ZENTAO_APP_CODE`。

**LLM 配置（必需，支持 OpenAI / DeepSeek / Ollama）：**

```ini
# 使用 DeepSeek（推荐，只需设置 provider 和 key）
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxx
# LLM_API_BASE 和 LLM_MODEL 可省略，自动使用 deepseek-chat

# 或使用 OpenAI
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-xxx
# LLM_MODEL=gpt-4o-mini

# 或使用本地 Ollama
# LLM_PROVIDER=ollama
# LLM_MODEL=qwen2.5:7b
```

DeepSeek 可选模型：
- `deepseek-chat` — 常规模型（默认，推荐用于用例生成）
- `deepseek-reasoner` — 推理模型（复杂项目分析时可选用）

验证连接：

```bash
testbot check-llm
testbot check-zentao
```

### 3. 运行

一键完整流程：

```bash
testbot full -p D:\Projects\your-project
```

分步执行（标准 CLI）：

```bash
testbot analyze -p D:\Projects\your-project
testbot plan   -p D:\Projects\your-project
testbot sync   .reports\cases_xxx.json
testbot run    -p D:\Projects\your-project --cases .reports\cases_xxx.json
testbot report .reports\cases_xxx.json .reports\report_xxx.json
```

推荐脚本（已内置在项目根目录）：

```bash
# 生成并同步用例
write_cases.bat   # Windows
./write_cases.sh  # Linux/macOS

# 执行并回写（默认 Playwright）
execute_cases.bat
./execute_cases.sh

# 若中断，使用最新报告补提交到禅道
submit_latest.bat
./submit_latest.sh
```

离线模式（无 LLM，规则生成用例）：

```bash
testbot full --mode rule --no-llm
```

**全量覆盖**（为项目全部功能点生成用例，推荐大型项目）：

```bash
# .env 中设置 PLANNER_MODE=full，或命令行指定
testbot full --mode full
testbot plan --mode full
```

相关配置：

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_CASES_PER_FEATURE` | 3 | 每个功能点至少生成几条用例 |
| `LLM_FEATURE_BATCH_SIZE` | 5 | 每批处理几个功能点（越小越细、调用次数越多） |
| `LLM_INVENTORY_MAX_FILES` | 100 | 功能点盘点时扫描的文件数 |
| `LLM_MAX_TOKENS` | 4096 | 建议全量模式设为 8192 |

**自动执行并登记禅道**（已有 500+ 条用例时）：

```bash
# 1. 在 .env 中设置执行模式
EXECUTOR_MODE=playwright   # 或 llm / auto / framework
LLM_EXEC_BATCH_SIZE=10     # 每批执行几条（500条约 50 次 LLM 调用）

# 2. 对已同步的用例文件执行 + 回写禅道
testbot execute .reports/cases_xxx.json --sync --executor playwright

# 或分步
testbot run --cases .reports/cases_xxx.json --executor playwright --sync
testbot report .reports/cases_xxx.json .reports/report_xxx.json
```

> 禅道回写需要账号具备「执行用例 / 登记结果」权限（testcase-run）。若报 user-deny，请联系管理员开通。

失败用例会自动在禅道 **提 Bug**（需 `ZENTAO_AUTO_CREATE_BUGS=true`，提 Bug 权限已在你环境验证可用）。

**Playwright 浏览器测试**：

```bash
pip install playwright
playwright install chromium

# .env 配置 TARGET_APP_URL、TARGET_APP_LOGIN_URL、TARGET_APP_USERNAME、TARGET_APP_PASSWORD
# EXECUTOR_MODE=playwright
testbot execute .reports/cases_xxx.json --sync --executor playwright
```

> `testbot execute` 需要输入 `cases_*.json` 文件。若你只有禅道里的用例，可先用导出脚本生成：  
> `python scripts/export_zentao_testcases.py --limit 50 --output .reports/cases_export.json`

## 架构

```
TestBot/
├── analyzer/     # 结构扫描 + LLM 项目理解
├── llm/          # OpenAI 兼容 LLM 客户端
├── planner/      # LLM 用例生成（llm/full）/ 规则生成（rule）
├── executor/     # framework / llm / playwright 执行
├── reporter/     # 报告 + 禅道回写 + 自动提Bug
├── zentao/       # 禅道 Session/REST 客户端
└── workflow/     # 流程编排
```

| 模块 | 是否用 LLM | 说明 |
|------|-----------|------|
| 项目理解 | ✅ | 阅读源码，识别核心功能与风险 |
| 用例设计 | ✅ | 生成具体可执行的测试步骤 |
| 测试执行 | ✅/❌ | `llm` 与 `playwright` 使用 LLM；`framework` 为确定性执行 |
| 禅道同步 | ❌ | Session/REST（按版本自动选择） |

## 开发

```bash
pip install -e ".[dev]"
pytest
```
