# 05 · 多 Agent 接入架构规划（后期）

> 状态：**规划稿，尚未实施**。当前代码仍只有 ZCode 一个数据源。
> 本文的作用是让后续实施有据可依，避免又出现"文档说有、实际没有"的机制。

---

## 1. 目标

桌宠的状态**只反映所有 agent 的活动总数**，不反映"哪个 agent"；而"都有哪些 agent 在贡献"通过**独立的文本通道**呈现，不污染状态本身。

```
状态  = f(总数)              ← 决定播哪个动画
归属  = g(谁贡献了这些数)     ← 决定显示哪些名字
```

**验收标准**：同时开 ZCode(2 会话) + OpenCode(1 会话) → 动画是"全力奔跑中"(总数 3 ≥ 2)，归属显示 `ZCode 2 · OpenCode 1`。

---

## 2. 为什么现在做这件事（实测依据）

2026-10-13 实测三家数据源，**差异比"换个路径"大得多**：

| | ZCode | OpenCode | WorkBuddy |
|---|---|---|---|
| 库 | `~/.zcode/cli/db/db.sqlite` **334.6 MB** | `~/.local/share/opencode/opencode.db` **383.3 MB** | `~/.workbuddy/workbuddy.db` **1.6 MB** |
| 会话表 | `session`（有 `task_type` 列） | `session`（**无** `task_type`） | **`sessions`**（复数） |
| 运行中工具 | ✅ `tool_usage.status='running'` | ❌ **无 `tool_usage` 表** | ❌ 无 |
| 未读 | `tasks.unread_at`（**第二个库**） | ❌ 无 | ✅ `sessions.unread` 列 |
| 进程信号 | ✅ `ZCode.exe` | ⚠️ CLI 模式**无常驻进程** | ✅ `WorkBuddy.exe` |
| 备用信号 | — | `message/part.data` 是 JSON TEXT（**不建议解析**） | `projects/*/*.jsonl` mtime 增量（44 个） |

**关键结论：OpenCode 根本没有 ZCode 那个"正在跑的工具"信号。** 这决定了 Snapshot 必须携带"信号质量"，不能只有数值。

---

## 3. 分层

```
┌─ adapters/<agent>/probe.js ─ 每个 agent 一个，只读，无状态语义 ─┐
│   probe() → Snapshot                                            │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─ policy.js ─ 全局唯一，完全不知道"agent"是什么 ────────────────┐
│   Snapshot[] → { state, attribution[] }                         │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─ renderer/pet.js ─ 不变：state → 帧，attribution → 文本 ──────┐
```

**为什么 policy 必须唯一**：「2 个会话 = 全力跑」是**人**的直觉，不是某个 agent 的属性。三个 agent 各写一套策略 = 三倍的口径漂移风险（这个项目已经被状态口径坑过多次，见记忆条目 7/11/15）。

---

## 4. 数据契约

```js
/**
 * @typedef {Object} Snapshot
 * @property {string}  id            agent 标识
 * @property {boolean} alive         是否存活（见 §7：GUI 进程 或 store 活跃）
 * @property {?number} sessions      活跃会话数
 * @property {?number} toolsRunning  正在执行的工具数
 * @property {?number} unread        未读
 * @property {?number} errors        错误数
 * @property {Object}  signals       每个字段的来源可信度
 *           'exact'   精确，直接来自权威字段
 *           'approx'  代理指标（用活跃时间窗近似）
 *           'absent'  该 agent 没有这个信号 → 必须用 null，不能填 0
 * @property {?string} probeError    探测异常（只进日志，不进 UI）
 */
```

**`signals` 是这个设计的核心。** 若 OpenCode 报 `toolsRunning: 0`（而不是 `null` + `'absent'`），policy 会把它误判为"空闲"，于是同时开 ZCode 和 OpenCode 时 OpenCode 永远不出现在任何忙碌状态里 —— 一个不会报错、只会让宠物变笨的 bug。

**每个 probe 必须 fail-soft**：库不存在 / 被锁 / 列改名 / 权限不足 → 捕获、填 `probeError`、其余字段降级为 `null`，**绝不让桌宠整体崩掉**。这是 ZCode hook 失败"整块被拒"的教训。

---

## 5. 状态判定（总数口径）

```js
function decide(snaps) {
  const alive    = snaps.filter(s => s.alive);
  const total    = sum(alive.map(s => s.sessions ?? 0));
  const errors   = sum(alive.map(s => s.errors   ?? 0));
  const unread   = sum(alive.map(s => s.unread   ?? 0));

  if (!alive.length)                    return "sleeping";
  if (errors > 0)                       return "error";        // 最高优先
  if (unread > 0)                       return "notification";
  if (total >= 2)                       return "working";
  if (total === 1)                      return "walk";
  return "idle";
}
```

规则要点：
- **总数跨 agent 相加**，不分权重
- **error 覆盖一切**（沿用现有语义）
- **sleeping 的条件是"所有启用的 agent 都不存活"**，不是"ZCode 不在"
- 若所有 adapter 的 `sessions` 都是 `'absent'`，退化路径为：`total=0 → idle`，并在日志里告警一次（不要每次轮询都刷）

---

## 6. 归属呈现（谁在贡献）

### 6.1 只显示**贡献者**，不显示所有存活者

同时开着 3 个 agent 但只有 1 个在干活时，归属只应显示那 1 个。把全部存活 agent 都列出来是噪音。

```js
function attribute(snaps, state) {
  const key = state === 'error' ? 'errors' : state === 'notification' ? 'unread' : 'sessions';
  return snaps
    .filter(s => s.alive && (s[key] ?? 0) > 0)
    .map(s => ({ id: s.id, n: s[key] }))
    .sort((a, b) => b.n - a.n);            // 贡献量降序
}
```

### 6.2 UI：状态文字保持干净，归属另起一行

```html
<div id="label">全力奔跑中</div>       <!-- 只放状态，不塞 agent 名 -->
<div id="agents" class="hidden"></div> <!-- 归属：ZCode 2 · OpenCode 1 -->
```

理由：状态文案要短、要一眼可读；agent 名放进去会让文字长度随 agent 数跳动，破坏"文字一变化就说明状态变了"的可读性。

### 6.3 展示规则

| 情况 | 显示 |
|---|---|
| 0 个贡献者 | 隐藏（idle 没人需要解释） |
| 1 个贡献者 | `ZCode 2`（仍要显示数量，因为状态是总数口径） |
| 2~3 个 | `ZCode 2 · OpenCode 1` |
| >3 个 | `ZCode 3 · +2`（折叠，避免撑破窗口） |
| 名称过长 | 取 displayName，超 6 字截断 |

- **顺序必须稳定**：同分时按配置文件里的固定顺序排，否则每轮轮询顺序抖动会让文字闪烁
- 新增设置项 `showAgents`（布尔，默认 true），关掉即只留纯状态

### 6.4 后续可扩展的提示通道（不在本次范围）

- agent 色点（每个 agent 一个固定色，圆点数组）
- 鼠标悬停显示明细（`ZCode 2 · OpenCode 1`，展开为每个 agent 的会话标题）

先做文本，别一上来就做花哨的 —— 文字通道已经能回答"都有哪些 agent"。

---

## 7. 生命周期与看门狗

**存活（liveness）与活动（activity）必须分开**：

| agent 类型 | 存活判定 |
|---|---|
| GUI 应用（ZCode / WorkBuddy / DeepSeek 桌面版） | 进程存在 |
| CLI（opencode TUI / `opencode run`） | **没有常驻进程** → 退化为"store 最近有写入" |

**看门狗必须走同一个注册表**：`pet-watchdog.ps1` 现在硬编码 `Get-Process -Name ZCode`。加 agent 时若忘了改看门狗，就会出现"桌宠在、但永远不自己起来"——极难排查。目标形态是看门狗问注册表："任一启用的 agent 存活 → 拉起桌宠"。

**退出策略**：`followZcode` 泛化为 `followAgents`，语义 = 所有启用的 agent 都不存活时退出。当前实测退出时延 1.83s（900ms × 2 次 + tasklist 开销），泛化后每个 adapter 自己决定探测方式与周期。

---

## 8. 配置文件

`pet/agents.json`（外置，用户可编辑，不把 agent 列表写死在代码里）：

```json
{
  "agents": [
    { "id": "zcode",     "enabled": true, "displayName": "ZCode",
      "processNames": ["ZCode.exe"], "order": 1 },
    { "id": "opencode",  "enabled": false, "displayName": "OpenCode",
      "processNames": ["opencode-desktop.exe"], "order": 2,
      "note": "CLI 模式无进程，liveness 走 store 活跃度" },
    { "id": "workbuddy", "enabled": false, "displayName": "WorkBuddy",
      "processNames": ["WorkBuddy.exe"], "order": 3 }
  ]
}
```

`order` 字段就是 §6.3 里"同分时稳定排序"的依据。

---

## 9. 分阶段落地

| 阶段 | 内容 | 风险 | 验证方式 |
|---|---|---|---|
| **1** | 纯重构：抽 `adapters/` + 注册表 + policy，**只放 zcode 一个 adapter** | **零行为变化** | 现有 8 态行为逐条比对 + capturePage 截图回归 |
| **2** | 解决大库开销（334MB + 383MB 每 2s 打开 = 翻倍） | 中 | 测量轮询耗时；考虑持久化只读连接或错开轮询 |
| **3** | 加 `opencode` adapter | 低 | 降级到只用 `session.time_updated` 活跃窗 |
| **4** | 加归属呈现（§6） | 低 | 三 agent 同开时的文案正确性 |
| **5** | 加 WorkBuddy / DeepSeek | 中 | WorkBuddy 已探明；**DeepSeek 未探明，需先确认是桌面版还是 CLI** |

**阶段 1 是硬性前置**：它是零风险的，而且做完之后每加一个 agent 都只是"写一个文件"。跳过阶段 1 直接加 agent，会把重构风险和行为变更风险叠在一起，出问题无法二分定位。

---

## 10. 风险登记

| 风险 | 触发条件 | 对策 |
|---|---|---|
| **大库开销翻倍** | 两个 300MB+ 库每 2s 打开 | 阶段 2 先处理；连接复用 |
| **schema 随版本变** | 上游改列名（如 WorkBuddy `session`→`sessions`） | fail-soft + `signals` 标记 + 启动时打一行 schema 摘要到日志 |
| **会话数虚高** | 直接 `COUNT(*)` 会把 archived/completed 也算进去（WorkBuddy 实测 45 个全是 archived/completed） | **必须加活跃时间窗过滤**，这是最容易静默出错的地方 |
| **重复计数** | 同一 agent 被登记两次 | 注册表按 `id` 去重，加载时校验 |
| **看门狗与代码不同步** | 加 agent 忘改看门狗 | 看门狗读同一份 `agents.json` |
| **解析 JSON blob** | 想从 `part.data` 取工具状态 | **禁止**，只读窄列；JSON 解析开销大且 schema 不稳定 |

---

## 11. 明确不做的事

- ❌ 每个 agent 一只独立宠物（用户已明确要总数口径的单一状态）
- ❌ 按 agent 优先级抢占状态（会与"总数"语义冲突）
- ❌ 解析 `message/part.data` / `model_usage.raw_usage_json` 等 JSON blob
- ❌ 以任何形式写入 agent 的数据库（探针一律 `readOnly`）
- ❌ 替 agent 做事（只读观察，不干预会话）

---

## 附：本文的实测方式

```powershell
python tools\probe\probe_agents_schema.py    # 三家表结构 + 候选信号是否存在
python tools\probe\probe_agents_detail.py    # 完整列清单 + 状态分布
```

两个脚本均以 `mode=ro` 只读打开，绝不写入 agent 的库。阶段 3 开工时应把它们固化为回归测试，防止上游改 schema 后静默失效（"信号消失"不会报错，只会让宠物变笨）。