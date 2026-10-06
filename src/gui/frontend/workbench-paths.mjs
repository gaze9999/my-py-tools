import { existsSync, readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

export function workbenchPaths(command, project = projectRoot) {
  const assets = command === 'serve'
    ? resolve(project, '../workbench-ui/src')
    : resolve(project, 'src/gui/resources/workbench')
  if (command !== 'serve') {
    const pin = JSON.parse(readFileSync(resolve(project, 'workbench-ui.json'), 'utf8'))
    const manifest = JSON.parse(readFileSync(resolve(assets, 'manifest.json'), 'utf8'))
    if (pin.revision !== manifest.revision || pin.repository !== manifest.repository)
      throw Error('Prepared Workbench UI does not match workbench-ui.json; run sync-workbench.mjs again')
  }
  const module = resolve(assets, 'workbench-ui.mjs')
  const css = resolve(assets, 'workbench-ui.css')
  if (!existsSync(module) || !existsSync(css))
    throw Error('Workbench UI assets are missing; provide the adjacent checkout for development or prepare the pinned build assets')
  return { assets, alias: [
    { find: '@workbench-ui/style', replacement: css },
    { find: '@workbench-ui', replacement: module },
  ] }
}
