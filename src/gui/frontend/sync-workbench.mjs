// Delegate offline staging to the pinned toolkit's standard-library helper.
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const base = dirname(fileURLToPath(import.meta.url))
const project = resolve(base, '../../..')
const sourceFlag = process.argv.indexOf('--source')
if (sourceFlag < 0 || !process.argv[sourceFlag + 1]) throw Error('Usage: node sync-workbench.mjs --source <workbench-ui checkout>')
const source = resolve(process.argv[sourceFlag + 1])
const pythonFlag = process.argv.indexOf('--python')
if (pythonFlag >= 0 && !process.argv[pythonFlag + 1]) throw Error('--python requires an executable')
const python = pythonFlag < 0 ? 'python' : process.argv[pythonFlag + 1]
const packageInfo = JSON.parse(readFileSync(resolve(source, 'package.json'), 'utf8'))
if (packageInfo.name !== 'workbench-ui') throw Error('The source must be a workbench-ui checkout')
const pin = JSON.parse(readFileSync(resolve(project, 'workbench-ui.json'), 'utf8'))
const commit = execFileSync('git', ['-C', source, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
if (pin.version !== 1 || pin.repository !== 'gaze9999/workbench-ui' || !/^[a-f0-9]{40}$/.test(pin.revision) || commit !== pin.revision)
  throw Error('Workbench UI checkout does not match the reviewed source pin')
// Verify executable helper code before handing control to the shared source.
execFileSync('git', ['-C', source, 'diff', '--exit-code', commit, '--',
  'src', 'integrations/python/workbench_assets.py', 'package.json'])
const resources = resolve(base, '../resources')
execFileSync(python, ['-B', resolve(source, 'integrations/python/workbench_assets.py'),
  '--project', project, '--destination', resolve(resources, 'workbench'), '--source', source], { stdio: 'inherit' })
const manifest = JSON.parse(readFileSync(resolve(resources, 'workbench/manifest.json'), 'utf8'))
mkdirSync(resources, { recursive: true })
writeFileSync(resolve(resources, 'workbench-ui.json'), JSON.stringify({
  name: packageInfo.name, version: packageInfo.version,
  commit: manifest.revision, dirty: false, files: manifest.sha256,
}, null, 2) + '\n')
console.log(`Prepared pinned Workbench UI ${manifest.revision}`)
