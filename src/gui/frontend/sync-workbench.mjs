// Copy only the shared toolkit assets, never application-specific code or data.
import { readFileSync, copyFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const base = dirname(fileURLToPath(import.meta.url))
const sourceFlag = process.argv.indexOf('--source')
if (sourceFlag < 0 || !process.argv[sourceFlag + 1]) throw Error('Usage: node sync-workbench.mjs --source <workbench-ui checkout>')
const source = resolve(process.argv[sourceFlag + 1])
const packageInfo = JSON.parse(readFileSync(resolve(source, 'package.json'), 'utf8'))
if (packageInfo.name !== 'workbench-ui') throw Error('The source must be a workbench-ui checkout')
const target = resolve(base, 'src/vendor')
mkdirSync(target, { recursive: true })
const files = {}
for (const name of ['workbench-ui.css', 'workbench-ui.js', 'workbench-ui.mjs']) {
  const input = resolve(source, 'src', name)
  files[name] = createHash('sha256').update(readFileSync(input)).digest('hex')
  copyFileSync(input, resolve(target, name))
}
let commit = null
let dirty = null
try {
  commit = execFileSync('git', ['-C', source, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  dirty = Boolean(execFileSync('git', ['-C', source, 'status', '--porcelain', '--', 'src', 'package.json'], { encoding: 'utf8' }).trim())
} catch { /* Exported toolkit folders still have content hashes. */ }
const resources = resolve(base, '../resources')
mkdirSync(resources, { recursive: true })
writeFileSync(resolve(resources, 'workbench-ui.json'), JSON.stringify({ name: packageInfo.name, version: packageInfo.version, commit, dirty, files }, null, 2) + '\n')
console.log(`Prepared Workbench UI ${packageInfo.version}, ${dirty ? 'working-tree assets' : 'committed or exported assets'}`)
