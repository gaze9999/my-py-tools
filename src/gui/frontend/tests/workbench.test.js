import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { workbenchPaths } from '../workbench-paths.mjs'

function fixture(t) {
  const root = mkdtempSync(resolve(tmpdir(), 'workbench-paths-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const project = resolve(root, 'consumer')
  mkdirSync(project)
  const pin = { version: 1, repository: 'gaze9999/workbench-ui', revision: 'a'.repeat(40) }
  writeFileSync(resolve(project, 'workbench-ui.json'), JSON.stringify(pin))
  return { root, project, pin }
}

function assets(directory) {
  mkdirSync(directory, { recursive: true })
  for (const name of ['workbench-ui.mjs', 'workbench-ui.css']) writeFileSync(resolve(directory, name), 'fixture')
}

test('development reads adjacent shared sources without staged copies', t => {
  const { root, project } = fixture(t)
  const source = resolve(root, 'workbench-ui/src')
  assets(source)
  const paths = workbenchPaths('serve', project)
  assert.equal(paths.assets, source)
  assert.equal(paths.alias[0].replacement, resolve(source, 'workbench-ui.css'))
  assert.equal(paths.alias[1].replacement, resolve(source, 'workbench-ui.mjs'))
})

test('production reads pinned offline assets and rejects stale revisions', t => {
  const { project, pin } = fixture(t)
  const staged = resolve(project, 'src/gui/resources/workbench')
  assets(staged)
  writeFileSync(resolve(staged, 'manifest.json'), JSON.stringify(pin))
  assert.equal(workbenchPaths('build', project).assets, staged)
  writeFileSync(resolve(staged, 'manifest.json'), JSON.stringify({ ...pin, revision: 'b'.repeat(40) }))
  assert.throws(() => workbenchPaths('build', project), /does not match/)
})

test('missing shared sources fail clearly without downloading assets', t => {
  const { project } = fixture(t)
  assert.throws(() => workbenchPaths('serve', project), /assets are missing/)
})
