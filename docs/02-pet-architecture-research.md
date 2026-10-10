# 支线一：桌宠基础架构与框架调研

> 状态：✅ 第一阶段完成 ｜ 日期：2026-10-10 ｜ 数据：GitHub API 实测星数

## 1. 同类产品对比（GitHub 实测 2026-10-10）

| 项目 | ⭐ | 技术栈 | 定位与亮点 | 对本项目的可借鉴点 |
| --- | --- | --- | --- | --- |
| [ayangweb/BongoCat](https://github.com/ayangweb/BongoCat) | 23,888 | **Rust/Tauri v2** | 跨平台互动桌宠（键鼠联动），Tauri 桌宠天花板 | 窗口置顶/点击穿透参数组合、多平台分发 |
| [NanmiCoder/cc-haha](https://github.com/NanmiCoder/cc-haha) | 14,947 | TypeScript/Electron | Claude Code / AI Agent 桌面工作台（非桌宠） | AI Agent 桌面端的状态呈现设计 |
| [LorisYounger/VPet](https://github.com/LorisYounger/VPet) | 6,941 | C#/WPF | 虚拟桌宠模拟器，可内嵌任意 WPF 应用 | 插件化动画系统、工作/休息/睡觉日程状态机 |
| [rullerzhou-afk/clawd-on-desk](https://github.com/rullerzhou-afk/clawd-on-desk) | 6,411 | JavaScript/**Electron** | **同定位产品**：看护 Claude Code/Codex/Cursor 的像素桌宠，启动时自动注册 agent hooks，权限请求/进度通知 | **hooks 自动注册**、12 状态机、权限气泡、mini mode、click-through、PWA 手机镜像 |
| [SlimeBoyOwO/LingChat](https://github.com/SlimeBoyOwO/LingChat) | 2,338 | Rust | AI 沉浸式 Galgame 对话+桌宠，情绪化表情切换 | 情绪→表情映射（错误/成功触发不同表情） |
| [OpenPetsHQ/openpets](https://github.com/OpenPetsHQ/openpets) | 1,276 | TypeScript | 本地优先桌宠平台 + 插件 SDK | 插件 SDK 化的状态/动画扩展 |
| [Adrianotiger/desktopPet](https://github.com/Adrianotiger/desktopPet) | 1,157 | C# | eSheep 复刻，SVG 动画 + 行为树 | 自主行走行为（随机散步/爬窗沿） |
| [isHarryh/Ark-Pets](https://github.com/isHarryh/Ark-Pets) | 1,121 | Java/JavaFX + **Live2D** | 明日方舟桌宠，Live2D 模型驱动 | Live2D 路线的高表现力参照（成本高） |
| [ChaozhongLiu/DyberPet](https://github.com/ChaozhongLiu/DyberPet) | 997 | Python/**PySide6** | 桌宠框架（养成系统/多动画帧） | 帧动画组织方式、招式/状态表驱动 |
| Shimeji 系（[wl_shimeji](https://github.com/CluelessCatBurger/wl_shimeji) / [Shijima-Qt](https://github.com/pixelomer/Shijima-qt) 等） | 200± | C / C++ / Java | 经典桌面精灵的现代移植，XML 脚本描述动作 | 动作脚本化（XML 定义帧序列+位移+音效）的经典设计 |

**结论性观察**：① "桌宠看护 AI 编程 Agent" 这个细分赛道已被验证（clawd-on-desk 6.4k⭐，且原生支持 hooks 自动注册）；② Electron 与 Tauri 两条路线都有万星级成功案例；③ 高星项目普遍把**状态机+帧动画+低占用**做成核心工程问题。

## 2. 技术选型对比（Windows 11）

| 维度 | **Electron（推荐）** | Tauri v2 | 原生 Win32 layered window | Python Qt (PySide6) |
| --- | --- | --- | --- | --- |
| 透明+置顶+点击穿透 | `transparent:true`+`setIgnoreMouseEvents`，成熟；坑：需 `disableHardwareAcceleration` 防透明像素丢失、DPI 多屏要 `ensureOnScreen` | 同等能力，WebView2 合成，占用更低 | 最强控制、最小体积，但全部手写 | 透明窗口支持好，打包体积大 |
| 与 ZCode 生态互操作 | **Node 同语言**：hooks 脚本、SQLite、chokidar 文件监视、better-sqlite3 无缝 | Rust 侧做系统调用，hooks 脚本仍是外部 Node/PS | C/C++ | Python |
| 动画素材管线 | canvas/WebGL/ImageBitmap/视频解码全套现成（前一期已跑通 RVM 抠图帧+视频循环引擎） | WebView 同 HTML5 能力 | 自绘 | QPainter/帧动画 |
| 包体/内存 | 大（~14MB 应用+~150MB 运行） | 小（~5MB） | 最小 | 中 |
| 前期项目资产 | **直接复用**（透明窗口、帧引擎、托盘、hook 注册、打包链全部验证过） | 需重写 | 需重写 | 需重写 |

**选型结论：Electron**。理由：本产品的本质是"状态机驱动的帧动画浮窗"，Electron 的坑（透明丢失、DPI、内存）在前一期项目已有实测解法；与 ZCode hooks（Node/PowerShell 脚本）同生态；clawd-on-desk 同路线 6.4k⭐ 佐证。Tauri 列为观察项（BongoCat 23.9k⭐ 证明路线可行，若后续对包体/内存有硬要求再评估）。

## 3. 推荐架构

```
┌────────────────────────── main 进程（Node） ──────────────────────────┐
│  状态源采集层                     窗口/系统集成层                        │
│  ├─ SQLite 轮询器(2~5s)          ├─ BrowserWindow(transparent/alwaysOnTop)│
│  │   tasks-index.sqlite          │   └─ setIgnoreMouseEvents(穿透区)     │
│  │   → 未读/错误任务/running      ├─ Tray(菜单: 状态/换装/余额/退出)        │
│  ├─ hook 接收器(7事件→状态文件)    ├─ ZCode.exe 进程轮询(3s, 连续2次消失隐藏)│
│  ├─ 运行时目录增量监视(chokidar)   ├─ 开机自启(HKCU Run)                   │
│  └─ 状态机 FSM(优先级仲裁) ──────→ ├─ 单实例锁                               │
│        ↓ state {key,since,meta}  └─ 拖拽/置顶/屏内回弹                     │
└──────────────────────────────┬───────────────────────────────────────┘
                        IPC (state push / drag / click)
┌──────────────────────────────┴───────────────────────────────────────┐
│  渲染进程: 帧动画引擎(canvas+ImageBitmap, 只保留当前状态帧)              │
│    manifest.json(状态→帧序列/视频/fps/scale) + 交互(拖拽/戳击/落地点头)   │
└──────────────────────────────────────────────────────────────────────┘
```

## 4. 建议状态清单（对接主线监控接口）

| 优先级(高→低) | 状态 | 触发 | 素材（已备） |
| --- | --- | --- | --- |
| 1 | error | PostToolUseFailure hook / `task_status='error'` 新增 | error.png（红!） |
| 2 | notification | `tasks.unread_at` 非空计数增加 | notification.png（橙!） |
| 3 | waiting | PermissionRequest hook | waiting.png（?） |
| 4 | working | 回合内（UserPromptSubmit 开启、90s 静默兜底收口） | working.png（</>，待换跑步帧） |
| 5 | idle | 默认 | idle.png + idle-breathe.png 双帧 |
| 6 | sleeping | ZCode.exe 进程消失 | sleeping.png（Zzz） |

打断规则：高优先级短暂覆盖（error 3s 闪烁窗后回落 working）；同级切换需当前动画播完一循环；`notification` 在用户查看任务列表（unread 清零）后自动回落。

## 5. 可借鉴功能 Top10（第二阶段起逐步吸收）

1. **hooks 自动注册**（clawd-on-desk：启动时检测并代注册 agent hooks，免用户手配）
2. **权限请求气泡**：waiting 时点击桌宠直接跳转/代答
3. **完成庆祝动画**：Stop/成功终态触发一次性庆祝帧
4. **错误闪烁 + 点击看详情**：error 态点击展示最近 `turn_usage.error_type` 明细
5. **idle 随机小动作**：空闲期随机插播短动画（防呆滞）
6. **眼睛/身体跟随鼠标**：低成本高生命感
7. **mini mode / click-through 模式**：缩成小挂件或完全穿透不挡操作
8. **换装/多形象**：manifest 已按 character 维度预留
9. **随 ZCode 启动/退出显隐** + 开机自启（前一期三层方案：HKCU Run + 进程轮询 + hook 兜底拉起）
10. **余额/用量悬浮条**（前一期已实现 BigModel quota 接口，可复刻）

## 6. 内存与稳定性红线（前期项目实测教训）

- `app.disableHardwareAcceleration()`：透明立绘在 GPU 异态下会整体丢失（跑过 DX12 全屏游戏后必现）
- 帧引擎用 canvas+ImageBitmap，**只保留当前状态帧、切状态即释放**（实测渲染进程 559MB→55MB 稳态）
- 全局 `uncaughtException` 落盘日志，不弹错误框；拖拽定时器必须判 `isDestroyed()`
- 打包：electron-packager（electron-builder 符号链接权限在本机必败）+ 打包后原版 electron.exe 覆盖产物 exe（rcedit 改名 exe 会开机崩溃 0x80000003）
- 部署复制不用 robocopy（会写全零文件），用 python shutil + 全文件 md5 校验

## 7. 参考链接汇总

- [zai-org/ZCode](https://github.com/zai-org/ZCode)（监控对象本体，官方开源）
- [rullerzhou-afk/clawd-on-desk](https://github.com/rullerzhou-afk/clawd-on-desk)（同定位，hooks 原生）
- [ayangweb/BongoCat](https://github.com/ayangweb/BongoCat)（Tauri 路线标杆）
- [LorisYounger/VPet](https://github.com/LorisYounger/VPet) ｜ [OpenPetsHQ/openpets](https://github.com/OpenPetsHQ/openpets) ｜ [isHarryh/Ark-Pets](https://github.com/isHarryh/Ark-Pets)（Live2D） ｜ [ChaozhongLiu/DyberPet](https://github.com/ChaozhongLiu/DyberPet) ｜ [Adrianotiger/desktopPet](https://github.com/Adrianotiger/desktopPet) ｜ [SlimeBoyOwO/LingChat](https://github.com/SlimeBoyOwO/LingChat) ｜ [NanmiCoder/cc-haha](https://github.com/NanmiCoder/cc-haha)
- Shimeji 现代移植：[wl_shimeji](https://github.com/CluelessCatBurger/wl_shimeji) ｜ [Shijima-Qt](https://github.com/pixelomer/Shijima-qt)
