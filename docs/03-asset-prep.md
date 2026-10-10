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

## 3. 服务器生成管线（2026-10-11 补齐，接入用户 GPU 服务器）

用户服务器（192.168.20.20，2×A6000，ComfyUI :8188）已用于补齐真实姿态素材：

| 产物 | 路线 | 质量验收 |
| --- | --- | --- |
| celebrate / error / sleeping 真实姿态 | **EditPlus 单参考图编辑**（Qwen-Image-2.1-UC GGUF，35~60s/张），提示词=保持服装发型画风不变的姿态改写 | [qc-final-assets.png](img/qc-final-assets.png) 右三张 |
| working 跑步帧 17 帧 @16fps | **Wan2.2 Animate2 姿态驱动**：旧项目 jog 视频（768² 白底 17 帧）→ SDPose 提骨架（chibi 可用）→ `WanAnimate2ToVideo` 640²/20步 换装生成 → 逐帧键控 | [qc-final-assets.png](img/qc-final-assets.png) 左五张 |

工具链（`tools/gen/`，均入库）：`submit_editplus.py`（ComfyUI 提交客户端，代理免疫）→ `gen_poses.py` → `gen_run_video.py`（upload/skeleton/animate 三段，先骨架 QC 再采样）→ `key_frames.py`（逐帧洪泛键控 + alpha 时序平滑 0.25/0.5/0.25 + 主体连通域过滤 + **全帧统一 bbox 防位置跳动**）→ `finalize_assets.py`（整合 + manifest v2）。

**实测教训**：
- **RVM 在白衣银发 vs 白底上不可用**（首尾帧主体被吞、白裙黑洞）——旧项目"语义分割不受底色影响"的结论在低对比场景不成立；逐帧洪泛键控 + 时序平滑才是该素材类型的正解。
- Animate2 输出帧数会多于输入骨架帧（17→21，尾部为外推残影帧），须 `--frames` 截断。
- SaveVideo/UNETLoader 等节点在这版 ComfyUI 要求 `format`/`weight_dtype` 参数；提交失败只挂尾节点时，重提命中上游缓存秒级完成。

## 4. 剩余缺口

| 缺口 | 说明 | 计划 |
| --- | --- | --- |
| waiting / notification | 仍为气泡占位（`?` / 橙`!`），无真实姿态 | 同 EditPlus 管线补（低优先） |
| 换装/多形象 | manifest 已按 character 维度预留 | 需求触发时扩展 |
