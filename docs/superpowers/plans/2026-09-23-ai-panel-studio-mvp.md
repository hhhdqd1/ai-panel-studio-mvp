# AI Panel Studio MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可本地运行、以 DeepSeek 驱动且可演示完整讨论闭环的 AI 圆桌 Web App，并提供测试和真实开发记录。

**Architecture:** React/TypeScript 前端通过 REST 读取快照、通过 SSE 接收按讨论隔离的事件；FastAPI 后端把讨论、消息、洞察和事件写入 SQLite，再由单 worker 内的后台编排任务推进状态。DeepSeek 网关是唯一外部模型边界，测试以确定性假网关替代；事实风险只表示“待核实”，不作真实性认证。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic、aiosqlite、httpx、pytest、React、TypeScript、Vite、React Router、Vitest、Playwright、SQLite、SSE。

**Spec:** [已确认设计规格](../specs/2026-09-23-ai-panel-studio-design.md)

## Global Constraints

- 作业窗口约 72 小时、实际开发约 48 小时；先保证可运行闭环，再完成视觉和文档。
- 中文 UI；默认 4 位专家，可选 2～6 位；每次专家发言 1～2 句；主持人控制流程且发言顺序不固定。
- DeepSeek Key 只存在后端环境变量，不能出现在日志、事件、网页或 Git；模型 ID 由 `DEEPSEEK_MODEL` 配置。
- 单 FastAPI worker；SQLite WAL 和 busy timeout；同一讨论一次只允许运行一个任务，不同讨论可并行。
- 页面展示可公开的意图摘要，不请求、保存或展示隐藏推理；洞察的来源消息必须可定位。
- 事实风险标签只能是“记录冲突”“缺少可追溯依据”“待外部核实”等风险描述，不输出“真实/已核实”。
- 测试默认使用假网关，不消耗 API 配额；真实 API 冒烟测试单独手工运行。
- 至少五条可重复导入的高质量示例；提交必须包含 README、Prompt 记录、开发过程文档、测试和真实 Git 提交历史。

## Review Focus

以下五类输入/故障最可能伤害演示质量；其对应测试分别写在任务 1、2、5、7、6 中。

1. 空白、超长议题或 2～6 以外人数：返回 422，且不调用模型（任务 1）。
2. 模型返回空白/损坏 JSON、429 或超时：有限重试后进入可恢复失败状态，不泄漏 Key（任务 2）。
3. SSE 断线重连时旧事件重放：按序号补发且客户端只应用一次，不触发新模型调用（任务 7）。
4. 两场讨论同时运行：消息、洞察和模型上下文互不串台（任务 5）。
5. 无依据数字、虚构引文和纯意见混杂：仅对具体可核查断言给出待核实风险，意见不误报（任务 6）。

---

## 文件与职责

项目目前只有设计文档和 `.gitignore`。文件按责任划分；任务执行时只建立其需要的文件。

| 文件 | 职责 |
| --- | --- |
| `backend/pyproject.toml`、`backend/.env.example` | 后端依赖、测试配置、环境变量范例 |
| `backend/app/main.py`、`backend/app/api.py`、`backend/app/schemas.py` | 应用生命周期、HTTP/SSE 路由、输入输出契约 |
| `backend/app/db.py`、`backend/app/store.py` | SQLite 表结构、事务和按讨论 ID 过滤的数据访问 |
| `backend/app/model_gateway.py`、`backend/app/panel_service.py`、`backend/app/prompts.py`、`backend/app/fake_gateway.py` | DeepSeek 调用、阵容生成服务、结构化提示、确定性测试替身 |
| `backend/app/selector.py`、`backend/app/orchestrator.py` | 发言意愿评分、阶段与状态推进 |
| `backend/app/review.py`、`backend/app/events.py` | 洞察/事实风险的清洗校验、SSE 事件补发与通知 |
| `backend/app/seeds.py`、`backend/data/seed_examples.json` | 五条示例数据及幂等导入 |
| `backend/tests/` | 单元、API、并发、恢复及事件流测试 |
| `frontend/src/types.ts`、`frontend/src/api.ts` | 与后端共享的 JSON 形状、REST/SSE 客户端 |
| `frontend/src/pages/HomePage.tsx`、`frontend/src/pages/DiscussionPage.tsx` | 创建/列表页与状态驱动的讨论页 |
| `frontend/src/components/Roundtable.tsx`、`Transcript.tsx`、`Insights.tsx` | 圆桌、发言记录、洞察及事实风险 |
| `frontend/src/styles.css`、`frontend/src/App.tsx` | 桌面/移动布局、路由入口 |
| `frontend/tests/`、`frontend/e2e/` | 前端状态逻辑测试和浏览器闭环 |
| `README.md`、`docs/prompt-log.md`、`docs/workflow.md` | 运行/结构说明、核心 Prompt 记录、开发工作流 |

## 固定接口约定

后端 JSON 使用 snake_case，前端 TypeScript 保持相同字段名，避免无谓映射。`GET /api/discussions/{id}` 返回 `DiscussionSnapshot`，包含 `id, topic, expert_count, status, stage, agents, messages, insight, summary, last_event_seq, error_code`。消息有 `id, agent_id, sequence, stage, content`。事件有 `sequence, type, payload`，SSE 的 `id` 等于 `sequence`。`insight` 的 `consensus, disagreements, open_questions, claim_flags` 均为数组，条目携带 `message_ids` 或 `message_id`。讨论状态固定为 `generating_panel | awaiting_confirmation | running | summarizing | completed | failed`。前端只根据这些持久化状态渲染，不从按钮点击猜测后端是否成功。

后端核心接口在对应任务创建并从后续任务调用：`Store.create_discussion(topic: str, expert_count: int) -> str`、`list_discussions() -> list[dict]`、`get_snapshot(discussion_id: str) -> dict | None`、`replace_panel(discussion_id: str, agents: list[dict]) -> None`、`transition(discussion_id: str, expected: str, status: str, *, stage: str | None = None) -> bool`、`append_message(discussion_id: str, agent_id: str, stage: str, content: str) -> dict`、`save_insight(discussion_id: str, insight: dict) -> dict`、`append_event(discussion_id: str, event_type: str, payload: dict) -> int`、`events_after(discussion_id: str, after: int) -> list[dict]`、`fail(discussion_id: str, error_code: str, resume_point: str) -> None`。

`ModelGateway` 的异步方法为 `generate_panel(topic: str, count: int) -> list[dict]`、`propose_intent(agent: dict, context: dict) -> dict`、`generate_speech(agent: dict, context: dict, intent: dict) -> str`、`moderate(context: dict, kind: str) -> str`、`review(context: dict, message: dict) -> dict`、`summarize(context: dict) -> str`。`FakeGateway` 实现同一接口，提供 `calls: list[dict]` 以供测试断言。

上面是跨任务签名清单；具体方法体在所属任务中实现。`Store` 中每个写入方法使用单个短事务；涉及状态与事件同步的写入须在同一事务内更新 `last_event_seq`，不能先向客户端发布尚未提交的内容。模型网关只读该讨论的快照构建上下文。代码实现可以增加私有 helper，但不得改变上述公共签名和 JSON 名称而不同时改测试。

### Task 1: 后端最小可运行 API、议题校验与 SQLite 基础

**Files:** Create `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/db.py`, `backend/app/store.py`, `backend/app/schemas.py`, `backend/app/api.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/test_discussion_api.py`.

**Interfaces:** Produces `create_app(store: Store, gateway: ModelGateway | None = None) -> FastAPI`、`Store.create_discussion/list_discussions/get_snapshot` 和 `POST/GET /api/discussions`；后续任务扩展 `Store` 和路由。

- [ ] **Step 1: 写失败的 API 测试。** `backend/tests/test_discussion_api.py` 至少包含下列测试；用测试库的临时 SQLite 文件和 `httpx.ASGITransport`，断言无效输入时假网关调用次数为零。

```python
@pytest.mark.parametrize("body", [
    {"topic": "   ", "expert_count": 4},
    {"topic": "x" * 501, "expert_count": 4},
    {"topic": "教育公平", "expert_count": 1},
    {"topic": "教育公平", "expert_count": 7},
])
async def test_create_rejects_invalid_input(client, fake_gateway, body):
    response = await client.post("/api/discussions", json=body)
    assert response.status_code == 422
    assert fake_gateway.calls == []

async def test_create_and_list(client):
    created = await client.post("/api/discussions", json={"topic": "  AI 与教育  "})
    assert created.status_code == 201
    assert created.json()["status"] == "generating_panel"
    listed = await client.get("/api/discussions")
    assert listed.json()[0]["topic"] == "AI 与教育"
```

- [ ] **Step 2: 运行测试并确认因应用/路由不存在而失败。** Run: `cd backend && python -m pytest tests/test_discussion_api.py -q`; expected: collection error or 404, never a false PASS.
- [ ] **Step 3: 建立依赖、表结构与最小路由。** `CreateDiscussion` 应用如下校验；`db.py` 开启外键、WAL、busy timeout，创建六张表及同场唯一索引；`Store.create_discussion` 生成 UUID、状态 `generating_panel`，各次操作新建/关闭连接，不共享 SQLite cursor。

```python
class CreateDiscussion(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    expert_count: int = Field(default=4, ge=2, le=6)

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("议题不能为空")
        return value

@router.post("/discussions", status_code=201)
async def create_discussion(body: CreateDiscussion, request: Request):
    discussion_id = await request.app.state.store.create_discussion(body.topic, body.expert_count)
    request.app.state.schedule_panel(discussion_id)
    return {"id": discussion_id, "status": "generating_panel"}
```

`discussion` 表存 `id/topic/expert_count/status/stage/expert_turns/summary/last_event_seq/resume_point/error_code/created_at/updated_at`；`agent/message/event/insight/model_run` 都有 `discussion_id` 外键。`message` 与 `event` 各有 `(discussion_id,sequence)` 唯一索引。`conftest.py` 的 `fake_gateway` 是只有 `calls=[]` 的轻量 spy；初始 `schedule_panel` 仅维持生成状态，任务 2 接入生成任务；生产环境缺 Key 时任务 2 返回清晰错误。

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
CREATE TABLE IF NOT EXISTS discussion (
  id TEXT PRIMARY KEY, topic TEXT NOT NULL, expert_count INTEGER NOT NULL,
  status TEXT NOT NULL, stage TEXT, expert_turns INTEGER NOT NULL DEFAULT 0,
  summary TEXT, last_event_seq INTEGER NOT NULL DEFAULT 0,
  resume_point TEXT, error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  kind TEXT NOT NULL, name TEXT NOT NULL, title TEXT NOT NULL, stance TEXT NOT NULL,
  specialties_json TEXT NOT NULL, color TEXT NOT NULL,
  public_status TEXT NOT NULL DEFAULT 'waiting', public_intent TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS message (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  agent_id TEXT NOT NULL REFERENCES agent(id), sequence INTEGER NOT NULL,
  stage TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(discussion_id, sequence)
);
CREATE TABLE IF NOT EXISTS event (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  sequence INTEGER NOT NULL, type TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(discussion_id, sequence)
);
CREATE TABLE IF NOT EXISTS insight (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  version INTEGER NOT NULL, content_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(discussion_id, version)
);
CREATE TABLE IF NOT EXISTS model_run (
  id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL REFERENCES discussion(id),
  purpose TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
  latency_ms INTEGER, token_usage_json TEXT, error_code TEXT, created_at TEXT NOT NULL
);
```
- [ ] **Step 4: 运行任务测试和格式检查。** Run: `cd backend && python -m pytest tests/test_discussion_api.py -q`; expected: PASS。再运行 `python -m compileall app`，预期无语法错误。
- [ ] **Step 5: 提交。** Run: `git add backend && git commit -m "feat: establish discussion API and SQLite schema"`。

### Task 2: DeepSeek 网关与阵容生成/恢复

**Files:** Create `backend/app/model_gateway.py`, `backend/app/panel_service.py`, `backend/app/prompts.py`, `backend/app/fake_gateway.py`, `backend/.env.example`, `backend/tests/test_panel.py`, `backend/tests/test_gateway.py`; modify `backend/app/api.py`, `backend/app/main.py`, `backend/app/store.py`.

**Interfaces:** Consumes Task 1 的 `Store`；produces `DeepSeekGateway`, `FakeGateway`, `PanelService.generate(discussion_id: str) -> None`, `Store.replace_panel`, `Store.fail` 和 `POST /api/discussions/{id}/resume` 的阵容分支。`generate_panel(topic,count)` 恰好返回一位主持人和 count 位专家，字段为 `kind/name/title/stance/specialties/color`。

- [ ] **Step 1: 写失败测试。** 覆盖有效阵容、字段缺失、空响应、两次无效 JSON 后失败、429/超时重试、错误不包含 Key，以及失败阵容可恢复。

```python
async def test_panel_requires_exact_count(panel_service, fake_gateway, store):
    fake_gateway.panel = [{"kind": "host", "name": "主持人", "title": "主持人", "stance": "中立", "specialties": ["引导"], "color": "#4361ee"}]
    discussion_id = await store.create_discussion("城市交通", 4)
    await panel_service.generate(discussion_id)
    snapshot = await store.get_snapshot(discussion_id)
    assert snapshot["status"] == "failed"
    assert snapshot["resume_point"] == "generating_panel"

async def test_bad_json_is_bounded(gateway, mock_transport):
    mock_transport.add_json({"choices": [{"message": {"content": "{broken"}}]})
    with pytest.raises(ModelOutputError):
        await gateway.generate_panel("城市交通", 4)
    assert mock_transport.calls <= 3
```

- [ ] **Step 2: 运行测试确认失败。** Run: `cd backend && python -m pytest tests/test_panel.py tests/test_gateway.py -q`; expected: import error for missing gateway/service.
- [ ] **Step 3: 实现网关、严格校验和任务调度。** 网关使用 `httpx.AsyncClient(timeout=30.0)` 调用 `POST https://api.deepseek.com/chat/completions`，`Authorization: Bearer <server-side key>`，`response_format={"type":"json_object"}` 仅用于结构化步骤；对 429、5xx、超时和无效 JSON 最多 3 次尝试，指数短退避。使用 Pydantic `PanelResponse` 验证人数、唯一姓名、非空立场与专长；消息日志只存 `purpose/model/status/latency_ms/token_usage/error_code`。服务仅在校验全部通过后原子替换阵容并切到 `awaiting_confirmation`，否则调用 `store.fail(discussion_id, "invalid_panel", "generating_panel")`。`resume` 只接受 `failed`，按 `resume_point` 重新调度。`DEEPSEEK_API_KEY` 缺失时设置 `missing_api_key`，不把值回传。

```python
class AgentDraft(BaseModel):
    kind: Literal["host", "expert"]
    name: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    stance: str = Field(min_length=1, max_length=160)
    specialties: list[str] = Field(min_length=1, max_length=5)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")

class PanelResponse(BaseModel):
    agents: list[AgentDraft]

    @model_validator(mode="after")
    def unique_names(self):
        names = [agent.name.strip() for agent in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agent names must be unique")
        return self

def validate_panel(payload: dict, count: int) -> list[dict]:
    agents = PanelResponse.model_validate(payload).agents
    if len(agents) != count + 1 or sum(a.kind == "host" for a in agents) != 1:
        raise ModelOutputError("panel size mismatch")
    return [agent.model_dump() for agent in agents]

class ModelOutputError(Exception):
    pass
```

- [ ] **Step 4: 运行任务测试。** Run: `cd backend && python -m pytest tests/test_panel.py tests/test_gateway.py -q`; expected: PASS；检查 `rg -n 'DEEPSEEK_API_KEY' backend` 仅命中配置读取、示例和测试，不能命中硬编码密钥。
- [ ] **Step 5: 提交。** Run: `git add backend && git commit -m "feat: generate validated DeepSeek panels with recovery"`。

### Task 3: 独立、可复测的发言选择器

**Files:** Create `backend/app/selector.py`, `backend/tests/test_selector.py`.

**Interfaces:** Consumes `list[dict]` 意愿，每项含 `agent_id/wants_to_speak/action/target_message_id/relevance/novelty/urgency/public_intent`；produces `select_speaker(intents, recent_agent_ids, spoken_counts) -> dict | None`。每个评分字段在 0～1，超界值钳制。

- [ ] **Step 1: 写失败的纯函数测试。** 在同样相关性下，刚发言者降权；直接相关的新反驳可以胜出；无意愿时返回 `None`；列表次序反转不改变结果。

```python
def test_not_round_robin_and_order_independent():
    intents = [
        {"agent_id": "a", "wants_to_speak": True, "action": "answer", "relevance": .6, "novelty": .4, "urgency": .4},
        {"agent_id": "b", "wants_to_speak": True, "action": "challenge", "relevance": .9, "novelty": .9, "urgency": .8},
    ]
    assert select_speaker(intents, ["a"], {"a": 2, "b": 0})["agent_id"] == "b"
    assert select_speaker(list(reversed(intents)), ["a"], {"a": 2, "b": 0})["agent_id"] == "b"

def test_everyone_declines():
    assert select_speaker([], [], {}) is None
```

- [ ] **Step 2: 确认测试因函数缺失而失败。** Run: `cd backend && python -m pytest tests/test_selector.py -q`; expected: import error.
- [ ] **Step 3: 实现明确评分和稳定平局规则。** 有效意愿基分 `0.45*relevance + 0.30*novelty + 0.20*urgency`；`challenge` 且有 `target_message_id` 加 `0.08`；最近两次出现每次减 `0.18`；历史发言次数每次减 `0.03`，未发言加 `0.08`；最后按 `(-score, agent_id)` 排序，不依赖数组位置。意愿结果中只保留公开 `public_intent`，不允许 `reasoning` 等字段进入事件。

```python
def _unit(value: object) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0

def select_speaker(intents: list[dict], recent_agent_ids: list[str], spoken_counts: dict[str, int]) -> dict | None:
    eligible = [item for item in intents if item.get("wants_to_speak") is True]
    if not eligible:
        return None
    def score(item: dict) -> float:
        agent_id = item["agent_id"]
        value = .45 * _unit(item.get("relevance")) + .30 * _unit(item.get("novelty")) + .20 * _unit(item.get("urgency"))
        value += .08 if item.get("action") == "challenge" and item.get("target_message_id") else 0
        value -= .18 * recent_agent_ids[-2:].count(agent_id)
        value -= .03 * spoken_counts.get(agent_id, 0)
        value += .08 if spoken_counts.get(agent_id, 0) == 0 else 0
        return value
    return sorted(eligible, key=lambda item: (-score(item), item["agent_id"]))[0]
```

- [ ] **Step 4: 运行全部选择器测试。** Run: `cd backend && python -m pytest tests/test_selector.py -q`; expected: PASS。
- [ ] **Step 5: 提交。** Run: `git add backend/app/selector.py backend/tests/test_selector.py && git commit -m "feat: select speakers by intent and fairness"`。

### Task 4: 持久化事件与讨论发言主循环

**Files:** Create `backend/app/orchestrator.py`, `backend/tests/test_orchestrator.py`; modify `backend/app/store.py`, `backend/app/api.py`, `backend/app/fake_gateway.py`.

**Interfaces:** Consumes `Store`, `ModelGateway`, `select_speaker`；produces `Orchestrator.run(discussion_id: str) -> None`、`POST /api/discussions/{id}/start`。模型上下文只来自 `Store.get_snapshot(discussion_id)`。每次写入消息或 Agent 状态都生成同场递增事件。

- [ ] **Step 1: 写失败的完整假网关循环测试。** 确认先有主持人开场、至少两位专家非固定次序发言、消息序号递增、各专家发言 1～2 句、最终状态完成；重复 `start` 返回 409。

```python
async def test_start_is_idempotent_conflict(client, ready_discussion):
    first = await client.post(f"/api/discussions/{ready_discussion}/start")
    second = await client.post(f"/api/discussions/{ready_discussion}/start")
    assert first.status_code == 202
    assert second.status_code == 409

async def test_discussion_has_host_and_nonfixed_experts(run_to_completion):
    snapshot = await run_to_completion("教育评价")
    messages = snapshot["messages"]
    assert snapshot["status"] == "completed"
    assert messages[0]["agent_id"] == next(a["id"] for a in snapshot["agents"] if a["kind"] == "host")
    assert len({m["agent_id"] for m in messages if m["agent_id"] != messages[0]["agent_id"]}) >= 2
    assert [m["sequence"] for m in messages] == list(range(1, len(messages) + 1))
```

`run_to_completion(topic: str) -> dict` 是放在本任务 `test_orchestrator.py` 的测试 helper：创建讨论、用假网关生成阵容、调用 start，并等待 `completed/failed` 后读取快照；等待上限 10 秒，超时直接失败。

- [ ] **Step 2: 确认测试失败。** Run: `cd backend && python -m pytest tests/test_orchestrator.py -q`; expected: 404 on start or import error.
- [ ] **Step 3: 实现状态机、限额与事务。** `start` 原子 `transition(expected="awaiting_confirmation",status="running",stage="opening")`，成功才创建后台任务。主循环：主持人开场 → 每轮并行收集各专家意愿（单专家错误视作弃权）→ selector → 选中者生成并保存 1～2 句 → 更新轮次、阶段和公开状态 → 主持人按阶段或高优先问题追问 → 上限或目标达到时总结。阶段阈值：开场后 1～4 位专家发言为 Exploration、5～8 为 Challenge、9～12 为 Synthesis，随后 Closing；可因无新意或上限提前收尾。目标约 12 次专家发言、4～6 次主持人发言；硬上限 16 次专家发言、100 次模型调用、20 分钟（默认 4 专家完成 12 轮约需 80 次调用）。把每个已提交发言当作恢复检查点；不要在模型返回前预先增加 `expert_turns`。主持人结束语和 `summary` 是两步，最终状态 `completed`。

```python
async def collect_intents(gateway: ModelGateway, experts: list[dict], context: dict) -> list[dict]:
    results = await asyncio.gather(
        *(gateway.propose_intent(agent, context) for agent in experts),
        return_exceptions=True,
    )
    return [result for result in results if isinstance(result, dict) and result.get("wants_to_speak") is True]

def speech_is_short(text: str) -> bool:
    sentences = [part for part in re.split(r"[。！？!?]+", text.strip()) if part.strip()]
    return 1 <= len(sentences) <= 2 and len(text) <= 240
```

`Store.append_message` 在一个写事务里插入消息、增加同场 `message.sequence`、插入 `message.created` 事件并更新 `last_event_seq`。用同场 `asyncio.Lock` 防止同一讨论重复任务，不能用全局锁串行化不同讨论。此任务先以空洞察运行，任务 6 接入审查。
- [ ] **Step 4: 运行主循环及回归测试。** Run: `cd backend && python -m pytest tests/test_orchestrator.py tests/test_discussion_api.py -q`; expected: PASS。
- [ ] **Step 5: 提交。** Run: `git add backend && git commit -m "feat: orchestrate and persist live roundtable discussions"`。

### Task 5: 多讨论隔离、失败继续与服务重启

**Files:** Create `backend/tests/test_recovery_isolation.py`; modify `backend/tests/conftest.py`, `backend/app/orchestrator.py`, `backend/app/store.py`, `backend/app/api.py`, `backend/app/main.py`, `backend/app/fake_gateway.py`.

**Interfaces:** Consumes Task 4 的 `Orchestrator` 与 `Store`；produces `Store.mark_interrupted()`、`POST /api/discussions/{id}/resume` 的运行/总结分支。只有 `failed` 且具有 `resume_point` 的讨论可继续。

- [ ] **Step 1: 写失败的隔离/恢复测试。** 同时跑“教育”与“交通”两场，要求每场 topic 只出现在自己的模型请求和消息中。让第一次专家发言之后网关失败，再 `resume`，已保存消息 ID 保持不变、总消息序号不重复。模拟重启时 `running/summarizing` 转为 `failed`，`completed` 不变。

```python
async def test_two_discussions_do_not_share_context(service, recording_gateway):
    first, second = await asyncio.gather(service.run_topic("教育"), service.run_topic("交通"))
    for discussion_id, topic, other in [(first, "教育", "交通"), (second, "交通", "教育")]:
        calls = recording_gateway.contexts_for(discussion_id)
        assert calls and all(topic in call["topic"] for call in calls)
        assert all(other not in call["topic"] for call in calls)

async def test_resume_keeps_committed_messages(service, failing_once_gateway, store):
    discussion_id = await service.run_until_failure("教育")
    before = (await store.get_snapshot(discussion_id))["messages"]
    await service.resume(discussion_id)
    after = (await store.get_snapshot(discussion_id))["messages"]
    assert [message["id"] for message in after[:len(before)]] == [message["id"] for message in before]
    assert len({message["sequence"] for message in after}) == len(after)
```

`service` 是本任务加入 `conftest.py` 的测试用 Facade，提供 `run_topic(topic)->discussion_id`、`run_until_failure(topic)->discussion_id`、`resume(discussion_id)->None`；内部只调用真实 Store、PanelService、Orchestrator 和 API 服务，不直接拼接预期结果。`recording_gateway.contexts_for(id)` 记录网关收到的同场上下文。

- [ ] **Step 2: 运行测试，确认未实现恢复/隔离断言失败。** Run: `cd backend && python -m pytest tests/test_recovery_isolation.py -q`; expected: FAIL。
- [ ] **Step 3: 完成 checkpoint 恢复。** 每轮开始从同场快照构建上下文；异常时 `fail(discussion_id, error_code, resume_point)`，只记录错误码不记录 Key/原始敏感报文。`resume` 原子变更 `failed → running` 或 `failed → summarizing`；runner 根据最后已提交消息和 `expert_turns` 继续，若收尾消息已在 DB 中就只生成尚未提交的总结。应用启动时 `mark_interrupted()` 把未运行完的旧状态标失败，等用户点击继续。`asyncio.Semaphore(4)` 只约束并发模型调用，不约束所有讨论生命周期。

```python
async def resume_discussion(store: Store, runner: Orchestrator, discussion_id: str) -> bool:
    snapshot = await store.get_snapshot(discussion_id)
    if snapshot is None or snapshot["status"] != "failed":
        return False
    point = snapshot["resume_point"]
    if point not in {"running", "summarizing"}:
        return False
    if not await store.transition(discussion_id, "failed", point, stage=snapshot["stage"]):
        return False
    runner.schedule(discussion_id)
    return True
```

- [ ] **Step 4: 运行隔离、恢复及全部后端测试。** Run: `cd backend && python -m pytest -q`; expected: PASS。
- [ ] **Step 5: 提交。** Run: `git add backend && git commit -m "feat: isolate discussions and resume failed runs"`。

### Task 6: 共识、分歧与事实风险审查

**Files:** Create `backend/app/review.py`, `backend/tests/test_review.py`; modify `backend/app/orchestrator.py`, `backend/app/store.py`, `backend/app/prompts.py`, `backend/app/fake_gateway.py`.

**Interfaces:** Consumes `gateway.review(context,message) -> dict`；produces `sanitize_review(raw: dict, known_message_ids: set[str]) -> dict`、`Store.save_insight(discussion_id: str, insight: dict) -> dict`。每条专家发言后一次独立审查；审查失败只发 `insight.review_unavailable`，主循环继续。

- [ ] **Step 1: 写失败的审查和来源校验测试。** 审查结果中无来源 ID 的共识/分歧丢弃；虚构引文、无依据数字、记录矛盾保留风险；“我认为更公平”不标事实风险；重复风险合并；`clarified` 不改成 `verified`；审查调用失败不阻断总结。

```python
def test_review_keeps_only_sourced_items():
    raw = {
        "consensus": [{"text": "同意先试点", "message_ids": ["m1", "m2"]}, {"text": "不存在的共识", "message_ids": ["missing"]}],
        "disagreements": [], "open_questions": [],
        "claim_flags": [{"message_id": "m2", "quote": "增长 83%", "reason_code": "needs_external_check", "explanation": "未给出来源", "status": "open"}],
    }
    result = sanitize_review(raw, {"m1", "m2"})
    assert len(result["consensus"]) == 1
    assert result["claim_flags"][0]["status"] == "open"

def test_opinion_is_not_a_claim_flag():
    result = sanitize_review({"consensus": [], "disagreements": [], "open_questions": [], "claim_flags": [
        {"message_id": "m1", "quote": "我认为这样更公平", "reason_code": "needs_external_check", "explanation": "意见", "status": "open"}
    ]}, {"m1"})
    assert result["claim_flags"] == []
```

- [ ] **Step 2: 运行测试确认审查函数缺失。** Run: `cd backend && python -m pytest tests/test_review.py -q`; expected: import error。
- [ ] **Step 3: 实现审查提示、净化器和存储。** Prompt 要求仅抽取具体、影响结论、可核查的断言；原因码仅 `record_conflict / unsupported_source / needs_external_check`。净化器核对 `message_id`、去重 `(message_id,quote)`、截断摘录长度、过滤价值判断和模型虚构的 `verified` 状态，且“记录冲突”必须指出另一条已存消息 ID。`Store.save_insight` 写版本快照和 `insight.updated` 事件。主持人每阶段最多一次追问高风险断言；总结前把未解决风险放入模型上下文，并在页面独立展示待核实列表。

```python
ALLOWED_REASONS = {"record_conflict", "unsupported_source", "needs_external_check"}
OPINION_PREFIXES = ("我认为", "我觉得", "我主张", "应该", "更公平", "更重要")

def valid_flag(flag: dict, known_message_ids: set[str]) -> bool:
    quote = str(flag.get("quote", "")).strip()
    if flag.get("message_id") not in known_message_ids:
        return False
    if flag.get("reason_code") not in ALLOWED_REASONS or flag.get("status") not in {"open", "clarified"}:
        return False
    if not 4 <= len(quote) <= 160 or quote.startswith(OPINION_PREFIXES):
        return False
    if flag["reason_code"] == "record_conflict":
        return flag.get("conflicts_with_message_id") in known_message_ids
    return bool(re.search(r"\d|《[^》]+》|[“\"][^”\"]+[”\"]|研究表明|数据显示|据.+报道", quote))
```

此函数仅是防止明显不合格标记的最低门槛，不能作为事实核验器。测试必须覆盖引文、日期、记录矛盾和纯意见，不能只信审查模型的自报标签。
- [ ] **Step 4: 运行审查及编排回归测试。** Run: `cd backend && python -m pytest tests/test_review.py tests/test_orchestrator.py -q`; expected: PASS。手查一次测试记录，不应出现“已核实”作为审查结论。
- [ ] **Step 5: 提交。** Run: `git add backend && git commit -m "feat: track sourced insights and unverified claim risks"`。

### Task 7: SSE 补发和前端事件去重契约

**Files:** Create `backend/app/events.py`, `backend/tests/test_events.py`; modify `backend/app/api.py`, `backend/app/store.py`。前端去重在任务 9 实现并测试。

**Interfaces:** Consumes `Store.events_after(discussion_id,after)`；produces `GET /api/discussions/{id}/events?after=N`，每个 SSE 帧为 `id: N`, `event: <type>`, `data: <JSON>`。浏览器事件 reducer 接受 `sequence > last_event_seq` 的事件。

- [ ] **Step 1: 写失败的事件补发测试。** 验证事件提交后才能读出、`after=1` 只得到序号大于 1 的事件、跨讨论没有事件、无效 `Last-Event-ID` 返回 422、短断线重连不调用模型。

```python
async def test_replay_is_scoped_and_ordered(store):
    first = await store.create_discussion("教育", 4)
    second = await store.create_discussion("交通", 4)
    await store.append_event(first, "discussion.status", {"status": "running"})
    await store.append_event(first, "message.created", {"id": "m1"})
    await store.append_event(second, "discussion.status", {"status": "running"})
    replay = await store.events_after(first, 1)
    assert [(event["sequence"], event["type"]) for event in replay] == [(2, "message.created")]
```

- [ ] **Step 2: 运行测试确认事件方法/路由失败。** Run: `cd backend && python -m pytest tests/test_events.py -q`; expected: FAIL。
- [ ] **Step 3: 实现补发与长连接。** 连接先按 `Last-Event-ID`，若缺失则用查询参数 `after`；下限为 0，非整数返回 422；循环读取同场 `events_after`，每条发 `id/event/data`，无新事件每 15 秒发 SSE 注释心跳；客户端断开后退出。事件发布在数据库提交后通过同场 `asyncio.Condition` 唤醒，轮询兜底也必须可用，避免通知丢失。

```python
def sse_frame(event: dict) -> str:
    return (
        f"id: {event['sequence']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
    )

def parse_after(header: str | None, query: str | None) -> int:
    raw = header if header is not None else query
    if raw is None:
        return 0
    value = int(raw)
    if value < 0:
        raise ValueError("after must be nonnegative")
    return value
```

- [ ] **Step 4: 运行事件/集成测试。** Run: `cd backend && python -m pytest tests/test_events.py tests/test_recovery_isolation.py -q`; expected: PASS。人工断开一次 EventSource 再接，确认 transcript 长度不增加。
- [ ] **Step 5: 提交。** Run: `git add backend && git commit -m "feat: replay durable per-discussion SSE events"`。

### Task 8: 首页、五条示例与前端 API 状态层

**Files:** Create `backend/data/seed_examples.json`, `backend/app/seeds.py`, `backend/tests/test_seeds.py`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/pages/HomePage.tsx`, `frontend/src/styles.css`, `frontend/tests/home.test.tsx`.

**Interfaces:** Consumes HTTP 契约；produces `/` 首页、`/discussions/:id` 路由容器。示例导入 `seed_examples(store) -> int` 幂等，种子讨论直接进入 `awaiting_confirmation`。`api.ts` 提供 `listDiscussions`, `createDiscussion`, `getDiscussion`, `startDiscussion`, `resumeDiscussion`。

- [ ] **Step 1: 写失败的种子与表单测试。** 五条示例各有议题和 1+4 位独特身份；重复导入不增加行数；前端空议题禁用提交、默认人数为 4、创建后导航到讨论 ID。

```python
async def test_seed_import_is_idempotent(store):
    assert await seed_examples(store) == 5
    assert await seed_examples(store) == 0
    rows = await store.list_discussions()
    assert len(rows) == 5
    assert all(row["status"] == "awaiting_confirmation" for row in rows)
```

```tsx
it('uses four experts and opens the created discussion', async () => {
  render(<HomePage />);
  await userEvent.type(screen.getByLabelText('讨论议题'), 'AI 与教育');
  await userEvent.click(screen.getByRole('button', { name: '创建圆桌' }));
  expect(createDiscussion).toHaveBeenCalledWith({ topic: 'AI 与教育', expert_count: 4 });
  expect(mockNavigate).toHaveBeenCalledWith('/discussions/test-id');
});
```

- [ ] **Step 2: 运行测试确认种子/前端缺失。** Run: `cd backend && python -m pytest tests/test_seeds.py -q`，然后 `cd frontend && npm test -- --run`; expected: 前者 import error，后者项目未建立。
- [ ] **Step 3: 写种子和最小前端。** 五个案例选不同领域（教育、城市交通、公共健康传播、开源 AI 治理、传统文化传播），每个含四位立场不同的专家和一个中立主持人；使用固定示例 ID 或唯一 `seed_key` 幂等导入。Vite 代理 `/api` 到本地 FastAPI；浏览器无 Key 输入框。首页列表清楚显示状态、时间和继续入口；输入框 trim、1～500 字符、专家数 2～6，错误显示原位。`createDiscussion` 明确发 snake_case JSON。

```ts
export type DiscussionStatus = 'generating_panel' | 'awaiting_confirmation' | 'running' | 'summarizing' | 'completed' | 'failed';
export type Agent = { id: string; kind: 'host' | 'expert'; name: string; title: string; stance: string; specialties: string[]; color: string; public_status: string; public_intent: string };
export type Message = { id: string; agent_id: string; sequence: number; stage: string; content: string };
export type Insight = { consensus: { text: string; message_ids: string[] }[]; disagreements: { text: string; message_ids: string[] }[]; open_questions: { text: string; message_ids: string[] }[]; claim_flags: { message_id: string; quote: string; reason_code: string; explanation: string; status: 'open' | 'clarified' }[] };
export type DiscussionSnapshot = { id: string; topic: string; expert_count: number; status: DiscussionStatus; stage: string | null; agents: Agent[]; messages: Message[]; insight: Insight; summary: string | null; last_event_seq: number; error_code: string | null };
export type DiscussionEvent =
  | { sequence: number; type: 'discussion.status'; payload: { status: DiscussionStatus; stage: string | null } }
  | { sequence: number; type: 'panel.ready'; payload: { agents: Agent[] } }
  | { sequence: number; type: 'agent.updated'; payload: { agent: Agent } }
  | { sequence: number; type: 'message.created'; payload: { message: Message } }
  | { sequence: number; type: 'insight.updated'; payload: { insight: Insight } }
  | { sequence: number; type: 'discussion.completed'; payload: { summary: string } }
  | { sequence: number; type: 'discussion.failed'; payload: { error_code: string } }
  | { sequence: number; type: 'insight.review_unavailable'; payload: { message_id: string } };
export type CreateDiscussionInput = { topic: string; expert_count: number };
export async function createDiscussion(input: CreateDiscussionInput): Promise<{ id: string; status: string }> {
  const response = await fetch('/api/discussions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(`创建失败（${response.status}）`);
  return response.json();
}
```

- [ ] **Step 4: 运行测试与构建。** Run: `cd backend && python -m pytest tests/test_seeds.py -q`；`cd frontend && npm test -- --run && npm run build`; expected: PASS。
- [ ] **Step 5: 提交。** Run: `git add backend frontend && git commit -m "feat: add seed roundtables and create/list UI"`。

### Task 9: 圆桌演播厅、实时记录、洞察与移动布局

**Files:** Create `frontend/src/pages/DiscussionPage.tsx`, `frontend/src/components/Roundtable.tsx`, `frontend/src/components/Transcript.tsx`, `frontend/src/components/Insights.tsx`, `frontend/src/discussionState.ts`, `frontend/tests/discussion.test.tsx`, `frontend/tests/discussionState.test.ts`; modify `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`.

**Interfaces:** Consumes Task 8 API 和 `DiscussionSnapshot`；produces detail page for all six states and `applyEvent(snapshot,event) -> snapshot`。SSE 首次连接从快照 `last_event_seq` 后补发；断线显示“正在重连”，不清空旧消息。

- [ ] **Step 1: 写失败的状态和 UI 测试。** `applyEvent` 重放同序号不增加发言；`agent.updated` 切换发言高亮；`message.created` 高亮同一条 transcript；事实风险链接跳到 `message_id`；`failed` 显示继续；`completed` 显示自然语言总结而非 JSON；窄屏标签能切圆桌/记录/洞察。

```ts
it('ignores replayed event sequences', () => {
  const first = applyEvent(baseSnapshot, {
    sequence: 2, type: 'message.created', payload: { message: newMessage },
  });
  const replay = applyEvent(first, {
    sequence: 2, type: 'message.created', payload: { message: newMessage },
  });
  expect(replay.messages).toHaveLength(first.messages.length);
  expect(replay.last_event_seq).toBe(2);
});
```

- [ ] **Step 2: 运行测试确认组件/函数缺失。** Run: `cd frontend && npm test -- --run`; expected: FAIL。
- [ ] **Step 3: 实现详情状态与圆桌布局。** `DiscussionPage` 获取一次快照后创建 `EventSource('/api/discussions/'+id+'/events?after='+last_event_seq)`；分别对约定的自定义事件名调用 `addEventListener`，解析为 `{sequence: Number(event.lastEventId), type, payload: JSON.parse(event.data)}`，调用纯 reducer，组件卸载时关闭连接。SSE 连续失败超过 10 秒时每 5 秒 GET 一次同场快照作为降级轮询，连接恢复后停止轮询；轮询只读，不启动模型。圆桌为重点区域：CSS Grid/绝对定位让主持人与专家围桌就座；当前发言席位整卡高对比填充、明显光晕、`aria-current`，举手另设图标；桌心展示当前问题，记录区同步强调最近发言。桌面圆桌/记录/洞察三区各自 `overflow:auto`，移动端以三标签切换。所有 Agent 状态只显示 `public_intent`，对 `reasoning/chain_of_thought` 等字段不定义类型也不渲染。

```ts
export function applyEvent(snapshot: DiscussionSnapshot, event: DiscussionEvent): DiscussionSnapshot {
  if (event.sequence <= snapshot.last_event_seq) return snapshot;
  if (event.sequence > snapshot.last_event_seq + 1) throw new Error('event gap: reload snapshot');
  const next = { ...snapshot, last_event_seq: event.sequence };
  switch (event.type) {
    case 'discussion.status': return { ...next, status: event.payload.status, stage: event.payload.stage };
    case 'panel.ready': return { ...next, agents: event.payload.agents, status: 'awaiting_confirmation' };
    case 'agent.updated': return { ...next, agents: next.agents.map(agent => agent.id === event.payload.agent.id ? event.payload.agent : agent) };
    case 'message.created': return { ...next, messages: [...next.messages, event.payload.message] };
    case 'insight.updated': return { ...next, insight: event.payload.insight };
    case 'discussion.completed': return { ...next, status: 'completed', summary: event.payload.summary };
    case 'discussion.failed': return { ...next, status: 'failed', error_code: event.payload.error_code };
    case 'insight.review_unavailable': return next;
  }
}
```

`DiscussionEvent` 在 `types.ts` 中按上述八类事件定义判别联合类型，保证各自 payload 属性可用；每一种在同一测试文件中有独立断言。若检测到事件序号跳跃，事件处理器重新获取快照；`EventSource` 自动重连时复用最后 ID。
- [ ] **Step 4: 运行前端测试、构建和人工视觉检查。** Run: `cd frontend && npm test -- --run && npm run build`; expected: PASS。分别以宽屏和 390px 窄屏打开一场假网关讨论，检查高亮显著性、各栏独立滚动、风险定位和无横向溢出。
- [ ] **Step 5: 提交。** Run: `git add frontend && git commit -m "feat: build responsive live roundtable studio"`。

### Task 10: 端到端验证、真实 API 冒烟及交付材料

**Files:** Create `frontend/e2e/roundtable.spec.ts`, `frontend/playwright.config.ts`, `README.md`, `docs/prompt-log.md`, `docs/workflow.md`, `docs/screenshots/desktop.png`, `docs/screenshots/mobile.png`; modify `backend/tests/` 和前端组件以修复验收发现的问题。

**Interfaces:** Consumes整个应用；produces 一键本地启动说明、可复跑的 E2E、至少五段真实 Prompt 记录、1～1.5 页工作流说明、待用户最终核对的提交清单。

- [ ] **Step 1: 写浏览器 E2E（先失败）。** Playwright 使用假网关与临时测试 DB；创建一场、确认阵容、实时看到高亮与 transcript、刷新后补接、风险定位、完成总结、窄屏标签切换。断言页面没有原始 JSON/隐藏推理字段。另一用例启动两场并检查数据隔离。

```ts
test('a roundtable survives refresh and reaches a natural summary', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('讨论议题').fill('教育与人工智能');
  await page.getByRole('button', { name: '创建圆桌' }).click();
  await expect(page.getByRole('button', { name: '确认阵容并开始' })).toBeVisible();
  await page.getByRole('button', { name: '确认阵容并开始' }).click();
  await expect(page.locator('[data-testid="transcript-message"]').first()).toBeVisible();
  await page.reload();
  await expect(page.getByText('讨论总结')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('chain_of_thought')).toHaveCount(0);
});
```

- [ ] **Step 2: 运行 E2E 确认至少一项因尚未配置或契约缺口而失败。** Run: `cd frontend && npx playwright test`; expected: FAIL，并记录真实失败原因，不人为制造失败。
- [ ] **Step 3: 补齐浏览器配置与交付文档，修复真实缺口。** README 包含依赖版本、安装/启动（后端一个 worker）、DeepSeek 环境变量、Vite 代理、SQLite 初始化和示例导入、Mermaid 架构/ER、API 列表、测试命令、并发/事实核验边界和截图。保存桌面/手机两张真实演示截图到 `docs/screenshots/`，不使用草图代替。`docs/prompt-log.md` 至少五段真实对话摘录及「目标→问题→修正→验证」，不要伪造未发生的 Prompt。`docs/workflow.md` 压缩到 1～1.5 页，真实说明 Codex 与 DeepSeek 职责、2～3 个真实难题和解决路径。真实 API 冒烟仅用后端本机 `.env`/进程环境，运行短讨论，记录耗时、费用风险、结构化输出、事实风险及总结质量；不记录 Key。邮箱地址和发送步骤只写入清单，不自动发送邮件。

```bash
cd backend
python -m pytest -q
cd ../frontend
npm test -- --run
npm run build
npx playwright test
```

- [ ] **Step 4: 完整复验。** 重跑上面四条命令，预期全 PASS；再检查 `git status --short`、`git log --oneline -12`、`rg -l 'sk-|DEEPSEEK_API_KEY=' --glob '!*.lock' .`（只列文件名，不输出疑似密钥内容），确保无实钥提交。手工真实 API 冒烟失败时明确记录阻塞，不把假网关结果当真实质量验收。
- [ ] **Step 5: 提交并准备用户审核。** Run: `git add README.md docs backend frontend && git commit -m "test: verify roundtable end to end and document delivery"`。向用户提供可运行命令、演示路径、测试结果及剩余风险；提交邮件由用户决定。

## 执行节奏与教学检查点

按 48 小时实际投入分配：任务 1–3 约 8 小时，任务 4–6 约 17 小时，任务 7–9 约 15 小时，任务 10 约 8 小时；每阶段保留真实失败修复缓冲，不把 72 小时全部排满。

- 任务 1–2：讲清楚“输入契约 → 数据持久化 → 模型边界”，让用户能独立解释为什么 Key 只在后端。
- 任务 3–6：讲清楚“每位专家独立表态 → 选择器 → 主持人控场 → 风险审查”，让用户能举例说明为何不是轮流发言、为何风险不等于事实判断。
- 任务 7–9：讲清楚“先读快照 → 再从序号补事件 → UI 去重”，让用户能解释刷新和 SSE 断线为何不会丢发言。
- 任务 10：用户亲自检查真实 API 演示、文档和提交包；我协助逐项修正，最终发送由用户决定。

每个任务提交后给用户一个短说明：本次可见成果、运行的验证、一个需要掌握的设计要点、下一任务目标。任务范围若因真实环境变化调整，先更新计划和测试再实施，不悄悄降低验收目标。
