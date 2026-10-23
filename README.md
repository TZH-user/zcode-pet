# ZCode Pet — an AI-assistant-aware desktop pet

<p align="center">
  <em>A Windows desktop pet that watches the state of the ZCode AI coding assistant and acts it out in real time — idle, working, waiting-for-confirmation, error, unread notification, sleeping.</em>
</p>

<p align="center">
  <img src="docs/img/qc-final-all2.png" alt="all states overview" width="640"/>
</p>

## Overview

ZCode Pet is a transparent always-on-top Electron window carrying a Q-version Luo Tianyi (hanfu) sprite that **reflects the live state of my AI coding assistant**: when a session runs, she sprints; when a task errors out, she panics; when ZCode exits, she sleeps. The state source reads ZCode's local session database directly (running sessions / unread / error tasks), so the pet is a tiny but real **system-integration project**: SQLite introspection, a state machine, a frame-animation engine, multi-DPI windowing, and a fully scripted asset pipeline.

> 🇨🇳 中文版说明见 [README_CN.md](README_CN.md)

## Highlights

- 🎭 **6 live states + walk** — working (sprinting) / idle / waiting-confirmation / error / unread-notification / sleeping, switched in real time from ZCode's session DB (tasks, sessions, turn usage tables)
- 🎬 **Pose-first asset pipeline** — 8 keyframes × 8-video batch generation, first/last-frame interpolation via an **MiniMax-H3 fl2va** client, plus a server pipeline (EditPlus poses + Animate2 run frames); walk v4 = 222 mirrored frames @ 20 fps (11.1 s loop)
- ✂️ **Automated matting & state derivation** — RVM (MobilenetV3) background removal, global-luminance black-key compositing fixes (closed black holes, premultiply edges, seam guards), manifest-driven state assets
- 🪟 **Solid window engineering** — transparent click-through, per-state adaptive window sizing (wide compositions no longer overflow), mixed-DPI dual-screen support, position memory with `ensureOnScreen` recovery
- 🐕 **Watchdog lifecycle** — a watchdog keeps the pet alive and starts/stops it together with ZCode

## Tech Stack

<div>
  <img src="https://img.shields.io/badge/Electron-39-47848F"/>
  <img src="https://img.shields.io/badge/Node.js-%3E20-339933"/>
  <img src="https://img.shields.io/badge/SQLite-session_source-003B57"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB"/>
  <img src="https://img.shields.io/badge/ONNX%20RVM-matting-FF6F00"/>
  <img src="https://img.shields.io/badge/MiniMax--H3-fl2va-8E44AD"/>
</div>

## Architecture

```
ZCode session DBs (sqlite: tasks-index / cli db)
        │  tools/zcode_state.py + pet/zcode_state.js (queries)
        ▼
  state machine (6 states + walk) ──► frame-animation engine
        │                                   │
        ▼                                   ▼
  Electron transparent always-on-top window + tray + drag
  (position memory · ensureOnScreen · per-state sizing · mixed-DPI)

assets pipeline (offline):
  raw art → RVM matting → make_states derivation → manifest.json
  pose-first: 8 keyframes → H3 fl2va first/last-frame videos → frame extraction
```

## Demos

| All states overview | Action overview |
|---|---|
| ![all states](docs/img/qc-final-all2.png) | ![actions](docs/img/current-actions-overview.png) |

More quality-check renders in [docs/img/](docs/img/).

## Repository Layout

```
pet/            # Electron app: main.js, preload, renderer, zcode_state.js
assets/sprites/ # state sprites + manifest.json (see NOTICE.md for character rights)
tools/          # asset pipeline: bg_remove.py, make_states.py, gen/* (H3 client),
                # monitor_console.py, zcode_state.py, watchdog
docs/           # 01 ZCode source analysis · 02 architecture research
                # 03 asset prep · 04 animation plan · 05 multi-agent architecture
启动桌宠.bat     # launcher
```

## Getting Started

```bash
cd pet
npm install        # Electron 39
npm start          # or double-click 启动桌宠.bat
```

Requires ZCode installed for live state; without it the pet simply idles/sleeps.

## Documentation

- ZCode session-monitor analysis: [docs/01-zcode-source-analysis.md](docs/01-zcode-source-analysis.md)
- Pet architecture research: [docs/02-pet-architecture-research.md](docs/02-pet-architecture-research.md)
- Asset preparation: [docs/03-asset-prep.md](docs/03-asset-prep.md)
- Animation plan: [docs/04-animation-plan.md](docs/04-animation-plan.md)

## License

- Source code (`pet/`, `tools/`, `docs/`): **MIT** © 2026 TZH-user — see [LICENSE](LICENSE)
- Character sprites (`assets/sprites/`): fan-made derivative art of Luo Tianyi, **non-commercial, not covered by MIT** — see [NOTICE.md](NOTICE.md)
