# 主线：ZCode 源码定位与会话监控接口分析

> 状态：✅ 第一阶段完成 ｜ 日期：2026-10-10 ｜ 源码快照：zai-org/ZCode v3.15.1（2026-10-10 更新）
> 本地克隆：`reference/zcode-src/`（浅克隆，已 gitignore，供后续阶段深挖）

## 1. 仓库定位结果

**官方已公开源码**：[github.com/zai-org/ZCode](https://github.com/zai-org/ZCode) —— "Z.ai's coding agent harness. Powerful, intelligent, extensible."

| 项 | 值 |
| --- | --- |
| Stars / 语言 / 许可 | 7,644 ⭐ / TypeScript / Apache-2.0 |
| 最新版本 | v3.15.1（2026-10-10 更新，官方声明仓库随版本持续同步） |
| 仓库形态 | pnpm monorepo |
| 官方插件市场 | [zai-org/zcode-plugins](https://github.com/zai-org/zcode-plugins) |

关键目录：

```
apps/zcode-cli/        Agent CLI 与运行时源码（核心）
packages/desktop/      Electron 桌面端（main 进程: taskRealtimeBus / host / scheduler）
packages/services/     会话/任务索引服务（zcodeTaskIndexSyncer / taskIndexRepo / hooksService）
packages/shared/       协议与类型（zcode-protocol-v4 / hooks.ts）
packages/ui/           渲染层（taskStatusUnreadSync 等任务列表逻辑）
docs/                  专题文档（desktop / plugins / monitoring / off-peak-task ...）
```

## 2. 总体架构与数据落盘

ZCode 桌面端 = Electron 宿主 + 内嵌 Agent CLI 运行时；会话状态**双数据库 + 运行时目录 + hooks 推送**四路并存（本机 `~/.zcode/` 实测）：

| 数据源 | 位置 | 内容 |
| --- | --- | --- |
| **任务索引库** | `~/.zcode/v2/tasks-index.sqlite` | 桌面端左侧任务列表的持久化投影：任务状态、**未读标记**、归档/置顶 |
| **会话主库** | `~/.zcode/cli/db/db.sqlite` | `session`（本机 177 个）、`message`/`part`、`turn_usage`、`tool_usage`、`model_usage`、`todo`、`session_input` 等 29 张表 |
| 运行时目录 | `~/.zcode/cli/agents/<sessId>/agent_*/` | 子代理 `output.txt`/`task.output`/`metadata.json`（文件增长 = 活动信号） |
| 历史导入 | `~/.zcode/v2/sessions/<工程hash>/claude-import-*.json` | Claude Code 导入会话（`meta`+`messages`，老数据噪声） |
| CLI 日志 | `~/.zcode/cli/log/zcode-*.jsonl` | 运行日志（config/hook 诊断） |

`tasks.task_id` 就是会话 ID（`sess_*`），两库通过它关联。

## 3. 会话状态机（源码证据）

**SessionPhase 枚举**（`packages/shared/src/zcode-protocol-v4/snapshot.ts:27-38`）：

```
draft（纯内存不落盘）→ prewarming → running → completedSuccess | completedInterrupted | error
```

**任务状态映射**（`packages/services/src/zcode-agent/zcodeTaskIndexSyncer.ts:199-213`）：

```ts
running/prewarming        → task_status "running"
completedSuccess/Interrupted → task_status "completed"
error                     → task_status "error"
```

**未读语义**（`zcodeTaskIndexSyncer.ts:206-216` + `packages/ui/src/lib/taskStatusUnreadSync.ts:57-76`）：
当会话进入**终态**（completed 且 goal 通过、或 error）且发生**在用户当前未查看的任务上**时，发出 `unreadSignal: "background_terminal"` → UI 调 `setTaskUnread` 写 `unread_at`。用户查看后清除；`last_unread_at` 保留上次未读时间（本机 148 条任务全有值）。

**实测校验**（2026-10-10 23:15）：本机 `task_status` 分布 = completed 114 / error 26 / NULL 8（NULL 全部为 8 月的 claude-import 老任务）；当前活跃会话行的状态是**上一回合的终态**（本会话因子代理失败标 error），说明 `running` 是瞬态标记，不能单独作为"运行中"判据。

## 4. Hooks 官方清单（源码证据）

`packages/shared/src/hooks.ts:5-13` —— **共 7 个事件**：

```
SessionStart / UserPromptSubmit / PreToolUse / PermissionRequest
/ PostToolUse / PostToolUseFailure / Stop
```

⚠️ **没有** `SessionEnd`、`Notification` 事件 —— "客户端退出"和"通知"不能靠 hook 感知（前者用进程轮询，后者读库）。其余旧结论仍成立：hooks 需嵌套在 `hooks.events.<事件>` 下、改后重启客户端生效、`Stop` 在带工具调用的回合不触发（源码 `Stop` 定义与实测一致，静默回退兜底）。

## 5. 实时监控接口清单

| 指标 | 数据来源 | 读取方式 | 实时性 | 可靠性 | 证据 |
| --- | --- | --- | --- | --- | --- |
| **运行中会话数** | ① `tasks` 表 `task_status='running'`（瞬态，单独用不可靠）② `tool_usage` 表 `status='running'` 行数（仅覆盖工具执行窗口）③ **hooks 推送**（UserPromptSubmit 开回合 / Stop 收口）+ `cli/agents/` 目录增量 | ②③ 组合：hook 事件开启回合窗口，90s 无增量/无新事件则视为结束 | 秒级 | 高（③已在前一期项目 35 分钟零误判实测） | tool_usage 实测有 running 行；hooks.ts:5-13 |
| **未读会话** | `tasks-index.sqlite` `tasks.unread_at`（NULL=无未读）+ `last_unread_at` | 只读轮询 SQLite（WAL 模式可并发读），`SELECT count(*) WHERE unread_at IS NOT NULL AND deleted=0 AND archived=0` | 轮询 2~5s | **高（官方权威字段，语义见 §3）** | tasks-index.sqlite 实测；taskStatusUnreadSync.ts |
| **错误会话** | ① `tasks.task_status='error'`（任务级，26 条实测）② `turn_usage.error_type`（model_error / unknown_error / turn_cancelled / model_context_exceeded）③ `tool_usage.status='error'`（工具级）+ **PostToolUseFailure hook 实时推送** | ①做列表、③做实时闪烁（hook 3s 窗口）、②做诊断明细 | 秒级（hook）/ 轮询（库） | 高 | turn_usage 实测 error 130 条；tool_usage error 252 条 |

## 6. 推荐接入方案（桌宠侧）

**SQLite 只读轮询 + hooks 推送混合**（桌面端没有对外的本地查询 API——源码中仅 `cloudContentService` 有 127.0.0.1 随机端口服务、`offPeakMockGateway` 是 mock，均非查询接口）：

1. **每 2~5s 只读打开两个库**（`file:...?mode=ro`，WAL 下不阻塞桌面端写入）：
   - 未读 = `tasks.unread_at IS NOT NULL AND deleted=0 AND archived=0 AND task_id LIKE 'sess_%'`（过滤 claude-import 噪声）
   - 错误任务列表 = `task_status='error'` 同上过滤
   - 运行中 = `tasks.task_status='running'` ∪ `tool_usage.status='running'` 计数
2. **hooks 推送**（7 事件注册到 `~/.zcode/config.json` 的 `hooks.events` 下）写每会话状态文件，回合窗口 + 90s 静默兜底判定"正在工作"（前一期已验证的口径）。
3. **ZCode 进程轮询**（tasklist）判 `sleeping`（hook 无 SessionEnd）。

风险与注意：
- 两库 schema 无稳定性承诺（`schema_migration` 表在持续演进），升级 ZCode 后需回归字段；
- `subagent_child` 会话在 `session` 表中单独存在，"会话数"口径要决定是否计入（建议不计入主计数、可做二级展示）；
- 只读连接避免 `db.sqlite-wal/-shm` 锁冲突；桌面端退出瞬间可能短暂锁库，需容错重试。

## 7. 证据文件路径清单

```
仓库内（reference/zcode-src/）:
  packages/shared/src/hooks.ts                              # HookEvent 7 事件枚举
  packages/shared/src/zcode-protocol-v4/snapshot.ts:27-38   # SessionPhase 枚举
  packages/services/src/zcode-agent/zcodeTaskIndexSyncer.ts:199-216  # 状态映射+unreadSignal
  packages/ui/src/lib/taskStatusUnreadSync.ts:57-76         # 未读标记判定
  packages/desktop/src/main/taskRealtimeBus.ts              # 桌面端任务实时总线
  packages/services/src/session/taskIndexRepo.ts            # 任务索引读写
本机（只读采样）:
  C:\Users/<user>\.zcode\v2\tasks-index.sqlite               # tasks 148 行: unread/task_status 实测
  C:\Users/<user>\.zcode\cli\db\db.sqlite                    # session 177 / turn_usage 823 / tool_usage 9735
  C:\Users/<user>\.zcode\cli\agents\sess_*\agent_*\          # 运行时输出目录
  C:\Users/<user>\.zcode\v2\sessions\<hash>\claude-import-*.json  # 导入历史
```
