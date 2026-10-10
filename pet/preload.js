"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pet", {
  onState: (cb) => ipcRenderer.on("pet:state", (_e, s) => cb(s)),
  loadFrames: (state) => ipcRenderer.invoke("pet:frames-load", state),
});
