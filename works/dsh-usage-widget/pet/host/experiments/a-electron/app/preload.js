// EXPERIMENT A preload: forwards page-side pointer events to the main process so the host can
// record, from the PAGE's point of view, whether a real click ever arrived.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('exp', {
  click: (p) => ipcRenderer.send('exp-click', p),
  move: (p) => ipcRenderer.send('exp-move', p),
})
