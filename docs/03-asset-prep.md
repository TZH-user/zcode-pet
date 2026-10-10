# 支线二：素材状态化准备

> 状态：✅ 第一阶段完成 ｜ 日期：2026-10-10

## 1. 原始素材清单

| 文件 | 规格 | 内容 |
| --- | --- | --- |
| `素材/洛天依汉服Q版.png` | 2880×2880 RGB 白底 | 洛天依 Q 版立绘，蓝白汉服，正面站姿，双臂微张 |

当前素材库为**单张静态立绘**，所有状态素材由它程序化衍生。

## 2. 处理管线

### 2.1 抠图透明化 — `tools/bg_remove.py`

- 原理：与背景色（四角中位数采样，实测 RGB≈252.5）欧氏距离 ≤ `--tol 30` 且饱和度 ≤ `--sat 30` 的像素为背景候选；scipy 连通域标记后**只清除与图像四边界连通的部分**，白色裙摆、浅蓝头发等封闭浅色区域自动保护。
- 边界 2px 羽化带按颜色距离做 alpha 渐变消白边；全透明像素回填背景色防止缩放彩边。
- 结果：清除 61.8% 背景，半透明像素仅 0.07%，深底目检（[qc-master-dark.png](img/qc-master-dark.png)）发梢/裙摆完整、无可见光晕。
- 产出：`assets/sprites/luotianyi/master.png`（2281×2670 透明原图，后续裁姿态的母本）。

### 2.2 状态衍生 — `tools/make_states.py`

基于 master 等比缩放到 512 高（437×512），程序化衍生 7 张状态图 + manifest：

| 状态 | 素材 | 衍生方式 | 对应 ZCode 事件（见主线文档） |
| --- | --- | --- | --- |
| `idle` | idle.png + idle-breathe.png 双帧 0.8fps | 底部锚定竖向放大 1.022 模拟呼吸 | 无活跃会话 |
| `working` | working.png（`</>`气泡） | 白底圆角气泡+代码符号 | UserPromptSubmit 回合运行中 |
| `waiting` | waiting.png（`?`气泡） | 同上（蓝） | PermissionRequest 等待确认 |
| `error` | error.png（红`!`气泡） | 同上（红） | PostToolUseFailure 等失败 |
| `notification` | notification.png（橙`!`气泡） | 同上（橙） | Notification / 未读会话 |
| `sleeping` | sleeping.png（Zzz） | 三级 Z 字母阶梯 | ZCode 客户端未运行 |

manifest（`assets/sprites/luotianyi/manifest.json`）：`states → {frames[], fps}` 结构，向前兼容多帧目录/视频字段；`stateHints` 记录每个状态的触发语义。

### 2.3 验收

- 深底状态拼图：[qc-states-dark.png](img/qc-states-dark.png) —— 气泡完整、Zzz 清晰、呼吸帧自然（初版气泡按 512 宽画布定位被右缘裁切，已按 437 实际宽度修正）。
- 经验（承接旧版项目教训）：透明素材验收一律用**深底合成目检**，不做屏幕截屏。

## 3. 缺口与第二阶段计划

| 缺口 | 说明 | 计划 |
| --- | --- | --- |
| working 动画 | 单立绘无法诚实表达"跑步/敲键盘"，当前为 `</>` 气泡占位 | 复用已验证的即梦图生视频 → 抽帧 → RVM 时序抠图管线（前一版项目已跑通），或 AI 生图多姿态 |
| 多姿态（拖拽/点击反应/庆祝） | 同上 | 第二阶段按 clawd-on-desk 状态清单（见支线一文档）补齐 |
| 换装/多形象 | 当前仅汉服一套 | manifest 已按 character 维度预留 |
