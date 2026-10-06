import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { workbenchPaths } from './workbench-paths.mjs'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ command }) => {
  const { assets, alias } = workbenchPaths(command)
  return {
    base: './',
    plugins: [react()],
    resolve: { alias },
    server: { host: '127.0.0.1', fs: { allow: [
      fileURLToPath(new URL('.', import.meta.url)),
      fileURLToPath(new URL('../assets', import.meta.url)), assets,
    ] } },
    build: {
      outDir: '../resources/web',
      emptyOutDir: true,
      target: 'es2020',
    },
  }
})
