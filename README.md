# ZCode 桌宠

一个悬浮于 Windows 桌面的 Q 版桌宠（洛天依·汉服形象），实时感知 ZCode（智谱 AI 编程助手）的运行状态并切换动画：空闲、工作中、等待确认、出错、有通知、休眠等。

## 阶段规划

- **第一阶段（当前）**
  - 主线：定位 ZCode 公开源码，分析可实时监控的会话接口（运行中会话数 / 未读会话 / 错误会话）→ `docs/01-zcode-source-analysis.md`
  - 支线一：桌宠基础架构与框架调研 → `docs/02-pet-architecture-research.md`
  - 支线二：素材状态化准备（抠图 / 状态衍生 / manifest）→ `docs/03-asset-prep.md` + `assets/`
- **第二阶段**：桌宠应用本体实现（透明窗口 / 状态机 / 动画引擎 / 托盘）
- **第三阶段**：会话状态实时接入与打磨

## 目录结构

```
├── docs/      第一阶段调研与分析文档
├── assets/    处理后的桌宠素材（sprites + manifest.json）
├── tools/     素材处理脚本
├── 素材/      原始素材（源头，只进不改）
└── reference/ 第三方参考（gitignore，不入库）
```
