import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { categoryName, initialLanguage, saveLanguage, translate, zhTW } from '../src/i18n.js'
import { englishTools, localizeTool } from '../src/tool-translations.js'

test('defaults to Traditional Chinese and validates saved language', () => {
  assert.equal(initialLanguage(), 'zh-TW')
  assert.equal(initialLanguage({ getItem: () => 'en' }), 'en')
  assert.equal(initialLanguage({ getItem: () => 'invalid' }), 'zh-TW')
  assert.equal(initialLanguage({ getItem: () => { throw Error('blocked') } }), 'zh-TW')
  assert.doesNotThrow(() => saveLanguage({ setItem: () => { throw Error('blocked') } }, 'en'))
})

test('missing or empty Chinese translations fall back to English', () => {
  assert.equal(translate('zh-TW', 'Ready'), '待命')
  assert.equal(translate('en', 'Ready'), 'Ready')
  assert.equal(translate('zh-TW', 'New English message'), 'New English message')
  assert.equal(translate('zh-TW', 'Ready', {}, { Ready: '' }), 'Ready')
  assert.equal(translate('zh-TW', 'Ready', {}, { Ready: '   ' }), 'Ready')
})

test('message values preserve paths and do not interpret replacement characters', () => {
  assert.equal(translate('zh-TW', 'Added {count} documents', { count: 2 }), '已加入 2 個文件')
  assert.equal(translate('en', 'Remove {file}', { file: '$& 中文.docx' }), 'Remove $& 中文.docx')
  assert.equal(translate('en', 'Failed, exit code {code}', { code: 0 }), 'Failed, exit code 0')
  assert.equal(categoryName('en', '文件處理'), 'Documents')
  assert.equal(categoryName('zh-TW', 'New Tools'), 'New Tools')
})

test('all interface message keys have Chinese translations', () => {
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
  for (const match of app.matchAll(/\bt\(['"]([^'"]+)['"]/g)) assert.ok(zhTW[match[1]], match[1])
  for (const match of app.matchAll(/\bkey: ['"]([^'"]+)['"]/g)) assert.ok(zhTW[match[1]], match[1])
})

test('built-in tool descriptions include complete English use cases', () => {
  assert.equal(Object.keys(englishTools).length, 16)
  for (const [id, english] of Object.entries(englishTools)) {
    const tool = { id, module: 'example.tool', name: '中文名稱', description: '中文說明', purpose: '中文用途', warning: '' }
    const localized = localizeTool('en', tool)
    for (const field of ['name', 'description', 'purpose', 'inputs', 'outputs', 'requirements']) assert.ok(localized[field], id + ':' + field)
    assert.equal(localized.name, english.name)
    assert.equal(localizeTool('zh-TW', tool).name, '中文名稱')
  }
})

test('new tool locale maps fall back field by field and survive language switches', () => {
  const tool = {
    id: 'new-tool', module: 'reports.new_tool', example_args: '--json',
    translations: { en: { name: 'New tool', description: 'English description' }, 'zh-TW': { name: '新工具' } },
  }
  assert.equal(localizeTool('zh-TW', tool).name, '新工具')
  assert.equal(localizeTool('zh-TW', tool).description, 'English description')
  assert.equal(localizeTool('en', tool).name, 'New tool')
  assert.equal(localizeTool('en', tool).example_args, '--json')
  assert.equal(tool.translations['zh-TW'].description, undefined)
  assert.ok(localizeTool('en', tool).search_text.includes('新工具'))
})
