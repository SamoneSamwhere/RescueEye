import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The repo also holds the Python API (with its virtualenvs and training runs)
// and the Android project, which carries a copy of the built app. Left to its
// defaults, Vite's dependency scan crawls every .html file in all of them and
// the file watcher tracks them too - minutes of startup for nothing.
const NOT_THE_WEB_APP = ['**/api/**', '**/android/**', '**/dist/**']

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    entries: ['index.html'],
  },
  server: {
    watch: { ignored: NOT_THE_WEB_APP },
  },
})
