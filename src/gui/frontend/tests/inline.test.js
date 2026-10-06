import test from 'node:test'
import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'

test('offline HTML embeds the original SVG favicon together with scripts and styles', () => {
  const root = mkdtempSync(join(tmpdir(), 'my-py-tools-icons-'))
  try {
    const frontend = join(root, 'frontend')
    const web = join(root, 'resources', 'web')
    mkdirSync(frontend)
    mkdirSync(join(web, 'assets'), { recursive: true })
    copyFileSync(new URL('../inline.mjs', import.meta.url), join(frontend, 'inline.mjs'))
    const svg = readFileSync(new URL('../../assets/app.svg', import.meta.url))
    writeFileSync(join(web, 'assets', 'app.svg'), svg)
    writeFileSync(join(web, 'assets', 'app.js'), 'window.example = true')
    writeFileSync(join(web, 'assets', 'app.css'), 'body { color: white }')
    writeFileSync(join(web, 'index.html'), '<link rel="icon" type="image/svg+xml" href="./assets/app.svg"><link href="./assets/app.css"><script src="./assets/app.js"></script>')
    execFileSync(process.execPath, [join(frontend, 'inline.mjs')])
    const html = readFileSync(join(web, 'index.html'), 'utf8')
    const icon = html.match(/href="data:image\/svg\+xml;base64,([^"]+)"/)
    assert.ok(icon)
    assert.deepEqual(Buffer.from(icon[1], 'base64'), svg)
    assert.match(html, /window.example = true/)
    assert.match(html, /body \{ color: white \}/)
    assert.ok(!html.includes('./assets/'))
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
