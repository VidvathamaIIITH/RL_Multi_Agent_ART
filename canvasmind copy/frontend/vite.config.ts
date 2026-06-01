import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// When CanvasMind is served behind a reverse proxy under a sub-path
// (e.g. https://host/dev-workspaces/<name>/proxy/3000/), asset URLs must NOT
// be absolute from the domain root, or the proxy prefix is lost and every
// asset 404s. Solutions:
//   - Production build (`npm run build`): base './' makes ALL asset paths
//     relative to the current page, so the proxy prefix is preserved
//     automatically. This is the recommended way to run on the VM.
//   - Dev server behind the proxy: set the full prefix explicitly, e.g.
//     VITE_BASE=/dev-workspaces/RAMA-GPU-A100/proxy/3000/ npm run dev
// Locally (no proxy) the default '/' is used and everything just works.
export default defineConfig(({ command }) => {
  const base = process.env.VITE_BASE || (command === 'build' ? './' : '/')

  return {
    base,
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      strictPort: true,
      open: false,
      // Let HMR work through an HTTPS reverse proxy when VITE_BASE is set.
      // The browser reaches the proxy on 443/wss; if HMR can't connect the
      // page still loads fully (you just refresh manually after edits).
      hmr: process.env.VITE_BASE
        ? { clientPort: 443, protocol: 'wss' }
        : true,
    },
    preview: {
      host: '0.0.0.0',
      port: 3000,
      strictPort: true,
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
    define: {
      'process.env.VITE_BACKEND_URL': JSON.stringify(process.env.VITE_BACKEND_URL || 'http://localhost:8000'),
      'process.env.VITE_WS_URL': JSON.stringify(process.env.VITE_WS_URL || 'ws://localhost:8000'),
    },
  }
})
