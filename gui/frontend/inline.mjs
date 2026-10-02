// Build a self-contained HTML resource for native WebView loading without a server.
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../resources/web')
const entry = resolve(root, 'index.html')
let html = readFileSync(entry, 'utf8')
html = html.replace(/<script\b[^>]*src="\.\/([^"]+)"[^>]*><\/script>/g, (_, file) =>
  '<script type="module">' + readFileSync(resolve(root, file), 'utf8').replaceAll('</script', '<\\/script') + '</script>',
)
html = html.replace(/<link\b[^>]*href="\.\/([^"]+\.css)"[^>]*>/g, (_, file) =>
  '<style>' + readFileSync(resolve(root, file), 'utf8') + '</style>',
)
if (html.includes('src="./assets/') || html.includes('href="./assets/')) throw new Error('GUI bundle still references external assets')
writeFileSync(entry, html)
