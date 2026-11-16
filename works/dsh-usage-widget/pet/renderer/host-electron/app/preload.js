const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('petHost', {
  info: () => ipcRenderer.invoke('pet:info'),
  setClickThrough: (on) => ipcRenderer.invoke('pet:click-through', !!on),
  setAlwaysOnTop: (on) => ipcRenderer.invoke('pet:always-on-top', !!on),
  move: (x, y) => ipcRenderer.invoke('pet:move', x, y),
  hitTest: (x, y) => ipcRenderer.invoke('pet:hit-test', x, y),
  quit: () => ipcRenderer.invoke('pet:quit'),
})
