import test from 'node:test'
import assert from 'node:assert/strict'
import { createBrowserBridge } from '../src/bridge.js'

test('browser requests use same-origin sessions and shared API argument arrays', async () => {
  const calls = []
  const host = { fetch: async (...args) => { calls.push(args); return { ok: true, json: async () => ({ value: 'result' }) } } }
  assert.equal(await createBrowserBridge(host).document_arguments(['a.txt'], 'source', '', true), 'result')
  assert.equal(calls[0][0], '/api/document_arguments')
  assert.equal(calls[0][1].credentials, 'same-origin')
  assert.deepEqual(JSON.parse(calls[0][1].body), [['a.txt'], 'source', '', true])
})

test('picker failure falls back to explicit paths, but invalid sessions never prompt', async () => {
  let prompted = 0
  const host = { document: { documentElement: { lang: 'zh-TW' } }, prompt: () => { prompted++; return '"C:\\path with space\\a.txt"' }, fetch: async () => ({ ok: false, status: 400, json: async () => ({ error: 'Native picker unavailable' }) }) }
  assert.deepEqual(await createBrowserBridge(host).choose_files(true), ['C:\\path with space\\a.txt'])
  host.fetch = async () => ({ ok: false, status: 403, json: async () => ({ error: 'Invalid local session' }) })
  await assert.rejects(createBrowserBridge(host).choose_files(true), /Invalid local session/)
  assert.equal(prompted, 1)
})
