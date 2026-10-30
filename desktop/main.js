const { app, BrowserWindow, Notification } = require("electron");
const path = require("path");

const START_URL = process.env.VERISONAR_URL || "http://localhost:3000";

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    backgroundColor: "#0b1f33",
    title: "VeriSonar",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.removeMenu();
  win.loadURL(START_URL);
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("browser-window-created", (_event, window) => {
  window.webContents.on("ipc-message", (_e, channel, payload) => {
    if (channel === "notify" && Notification.isSupported()) {
      new Notification({ title: payload.title || "VeriSonar", body: payload.body || "" }).show();
    }
  });
});
