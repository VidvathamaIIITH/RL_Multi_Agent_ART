import { ipcMain, shell } from 'electron'

export function registerIpcHandlers() {
  ipcMain.handle('open-external', async (_event, url: string) => {
    await shell.openExternal(url)
  })
}
