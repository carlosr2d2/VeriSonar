const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("verisonarDesktop", {
  platform: "windows",
  notify: (title, body) => ipcRenderer.send("notify", { title, body }),
});
