"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pet", {
  // ---- 既有通路（勿改签名，pet.js 依赖）----
  onState: (cb) => ipcRenderer.on("pet:state", (_e, s) => cb(s)),
  loadFrames: (state) => ipcRenderer.invoke("pet:frames-load", state),
  moveBy: (dx, dy) => ipcRenderer.send("pet:move-by", dx, dy),
  endDrag: () => ipcRenderer.send("pet:end-drag"),

  // ---- 右键菜单 / 设置 / 调试（接管会话新增）----
  // 走 IPC 主动请求而不是 webContents context-menu 事件：窗口是 frameless 且
  // body 带 -webkit-app-region:drag，右键事件在该区域不保证派发到主进程。
  openMenu: () => ipcRenderer.send("pet:open-menu"),
  reloadFrames: () => ipcRenderer.send("pet:reload-frames"),
  setOption: (key, value) => ipcRenderer.send("pet:set-option", key, value),
  getSettings: () => ipcRenderer.invoke("pet:get-settings"),
  onSettings: (cb) => ipcRenderer.on("pet:settings", (_e, s) => cb(s)),
});