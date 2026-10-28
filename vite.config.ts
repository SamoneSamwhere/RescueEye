import { rmSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// The repo also holds the Python API (with its virtualenvs and training runs)
// and the Android project, which carries a copy of the built app. Left to its
// defaults, Vite's dependency scan crawls every .html file in all of them and
// the file watcher tracks them too - minutes of startup for nothing.
const NOT_THE_WEB_APP = ['**/api/**', '**/android/**', '**/dist/**']

// public/downloads/ holds the APK the website offers for download. The Android
// app build (--mode mobile) must not pack the previous APK inside the new one.
function dropDownloadsFromApp(): Plugin {
  return {
    name: 'drop-downloads-from-app',
    apply: 'build',
    closeBundle() {
      rmSync(resolve('dist/downloads'), { recursive: true, force: true })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), mode === 'mobile' && dropDownloadsFromApp()],
  optimizeDeps: {
    entries: ['index.html'],
  },
  server: {
    watch: { ignored: NOT_THE_WEB_APP },
  },
}))
