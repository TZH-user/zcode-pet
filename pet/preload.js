"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pet", {
  onState: (cb) => ipcRenderer.on("pet:state", (_e, s) => cb(s)),
  loadFrames: (state) => ipcRenderer.invoke("pet:frames-load", state),
  moveBy: (dx, dy) => ipcRenderer.send("pet:move-by", dx, dy),
  endDrag: () => ipcRenderer.send("pet:end-drag"),
});
