import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { categoryName, initialLanguage, saveLanguage, translate } from './i18n'
import { localizeTool } from './tool-translations'

const bridge = () => window.pywebview.api

function Icon({ name, size = 18 }) {
  const paths = {
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    tools: <><path d="m4 5 5 5-3 3-5-5a6 6 0 0 0 8 8l6 6 4-4-6-6a6 6 0 0 0-8-8Z" /></>,
    file: <><path d="M14 2H5v20h14V7Z" /><path d="M14 2v6h5M8 13h8M8 17h6" /></>,
    folder: <path d="M2 6V4h7l3 3h10v13H2Z" />,
    play: <path d="m7 4 14 8-14 8Z" />,
    arrow: <><path d="M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6" /></>,
    terminal: <><path d="m4 5 6 7-6 7M12 19h8" /></>,
    copy: <><rect x="8" y="8" width="13" height="13" rx="2" /><path d="M16 8V3H3v13h5" /></>,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.tools}</svg>
}

function App() {
  const [language, setLanguage] = useState(() => {
    try { return initialLanguage(window.localStorage) } catch { return 'zh-TW' }
  })
  const t = useCallback((key, values) => translate(language, key, values), [language])
  useEffect(() => {
    document.documentElement.lang = language
    try { saveLanguage(window.localStorage, language) } catch { /* Use the session preference. */ }
  }, [language])
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const errorText = typeof error === 'string' ? t(error) : t(error.key, error.values)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [toolId, setToolId] = useState('document-to-markdown')
  const [args, setArgs] = useState('')
  const [cwd, setCwd] = useState('')
  const [python, setPython] = useState('')
  const [files, setFiles] = useState([])
  const [outputMode, setOutputMode] = useState('source')
  const [outputPath, setOutputPath] = useState('')
  const [dryRun, setDryRun] = useState(false)
  const [run, setRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState({ key: 'Ready' })
  const [output, setOutput] = useState('')
  const [stdin, setStdin] = useState('')
  const [dragging, setDragging] = useState(false)
  const [customArgs, setCustomArgs] = useState(false)
  const [command, setCommand] = useState('')
  const outputRef = useRef(null)
  const filesRef = useRef([])
  const running = Boolean(run?.running)
  const tools = useMemo(() => (data?.tools || []).map((item) => localizeTool(language, item)), [data, language])
  const tool = tools.find((item) => item.id === toolId)
  const isDocument = toolId === 'document-to-markdown'
  const visible = tools.filter((item) =>
    (category === '全部' || category === item.category) &&
    [item.name, item.module, item.description, item.purpose, item.search_text].join(' ').toLowerCase().includes(query.trim().toLowerCase()),
  )

  useEffect(() => {
    let disposed = false
    const initialize = async () => {
      try {
        const result = await bridge().bootstrap()
        if (disposed) return
        setData(result)
        setLanguage(result.defaults.language === 'en' ? 'en' : 'zh-TW')
        setCwd(result.defaults.cwd)
        setPython(result.defaults.python || '')
        setToolId(result.defaults.tool_id || 'document-to-markdown')
        setArgs(result.defaults.args || '')
        setFiles(result.defaults.files || [])
        filesRef.current = result.defaults.files || []
        if (result.warnings.length) setError(result.warnings.join('\n'))
      } catch (failure) { setError(String(failure.message || failure)) }
    }
    if (window.pywebview?.api) initialize()
    else window.addEventListener('pywebviewready', initialize, { once: true })
    const timeout = setTimeout(() => {
      if (!window.pywebview?.api) setError('Cannot connect to the desktop runtime. Restart the application')
    }, 12000)
    return () => {
      disposed = true
      clearTimeout(timeout)
      window.removeEventListener('pywebviewready', initialize)
    }
  }, [])

  useEffect(() => { filesRef.current = files }, [files])

  const addDocuments = useCallback(async (paths) => {
    try {
      const result = await bridge().normalize_documents([...filesRef.current, ...paths])
      setDragging(false)
      if (result.accepted.length) {
        filesRef.current = result.accepted
        setFiles(result.accepted)
        setToolId('document-to-markdown')
        setCategory('文件處理')
        setCustomArgs(false)
        setStatus({ key: 'Added {count} documents', values: { count: result.accepted.length } })
      }
      setError(result.rejected.length ? { key: 'Skipped unsupported or missing items: {paths}', values: { paths: result.rejected.join(', ') } } : '')
    } catch (failure) { setError(String(failure.message || failure)) }
  }, [])

  useEffect(() => {
    const drop = (event) => addDocuments(event.detail)
    window.addEventListener('native-files-dropped', drop)
    return () => window.removeEventListener('native-files-dropped', drop)
  }, [addDocuments])

  useEffect(() => {
    if (!data || !isDocument || customArgs) return
    let disposed = false
    bridge().document_arguments(files, outputMode, outputPath, dryRun).then((value) => {
      if (!disposed) setArgs(value)
    }).catch((failure) => setError(String(failure.message || failure)))
    return () => { disposed = true }
  }, [data, isDocument, customArgs, files, outputMode, outputPath, dryRun])

  useEffect(() => {
    if (!data || !tool) return
    let disposed = false
    bridge().preview_command(tool.id, args, python).then((value) => {
      if (!disposed) setCommand(value)
    }).catch((failure) => setError(String(failure.message || failure)))
    return () => { disposed = true }
  }, [data, tool, args, python])

  useEffect(() => {
    if (!running) return
    let disposed = false
    let timer
    const poll = async () => {
      try {
        const result = await bridge().run_status(run.run_id)
        if (disposed) return
        setRun(result)
        setOutput(result.output)
        if (result.running) timer = setTimeout(poll, 300)
        else setStatus({ key: result.exit_code === 0 ? 'Completed' : 'Failed, exit code {code}', values: { code: result.exit_code } })
      } catch (failure) {
        if (!disposed) { setError(String(failure.message || failure)); setStatus({ key: 'Unable to retrieve results' }) }
      }
    }
    poll()
    return () => { disposed = true; clearTimeout(timer) }
  }, [running, run?.run_id])

  useEffect(() => {
    const element = outputRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [output])

  const action = async (operation) => {
    try { setError(''); await operation() }
    catch (failure) { setError(String(failure.message || failure)) }
  }
  const chooseDocuments = () => action(async () => addDocuments(await bridge().choose_files(true)))
  const changeLanguage = (value) => {
    setLanguage(value)
    action(() => bridge().set_language(value))
  }
  const selectTool = (item) => {
    setToolId(item.id)
    setCategory(item.category)
    setArgs('')
    setCustomArgs(false)
    setError('')
  }
  const selectCategory = (value) => {
    setCategory(value)
    if (value !== '全部' && tool?.category !== value) {
      const first = data.tools.find((item) => item.category === value)
      if (first) selectTool(first)
    }
  }
  const execute = async (help = false) => {
    if (busy || running) return
    setBusy(true)
    setError('')
    try {
      if (!help && isDocument && !customArgs && (!files.length || (outputMode !== 'source' && !outputPath))) {
        throw new Error(!files.length ? 'Choose or drop documents first' : 'Choose an output location first')
      }
      const result = await bridge().start_tool(toolId, help ? '--help' : args, cwd, python)
      setOutput(result.output)
      setRun(result)
      setStatus({ key: 'Running' })
    } catch (failure) { setError(String(failure.message || failure)); setStatus({ key: 'Failed to start' }) }
    finally { setBusy(false) }
  }

  if (!data || !tool) return <div className="loading"><div className="brand-mark"><Icon name="tools" size={30} /></div><h1>My Py Tools</h1><p>{errorText || t("Preparing your tool workspace...")}</p></div>

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Icon name="tools" size={23} /></div><div><strong>My Py Tools</strong><span>{t("Local tool workspace")}</span></div></div>
        <div className="search"><Icon name="search" /><input aria-label={t("Search tools")} placeholder={t("Search tools or use cases")} value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <div className="section-label">{t('Tool categories')} <span>{data.tools.length}</span></div>
        <nav aria-label={t("Categories by purpose")}>{['全部', ...data.categories].map((item) => <button key={item} onClick={() => selectCategory(item)} className={category === item ? 'active' : ''}><span>{categoryName(language, item)}</span><small>{item === '全部' ? data.tools.length : data.tools.filter((entry) => entry.category === item).length}</small></button>)}</nav>
        <div className="section-label">{t("Tools")}</div>
        <div className="tool-list">{visible.length ? visible.map((item) => <button key={item.id} className={toolId === item.id ? 'selected' : ''} onClick={() => selectTool(item)}><strong>{item.name}</strong><span>{item.description}</span></button>) : <p className="empty">{t("No matching tools")}</p>}</div>
        <div className="sidebar-footer"><span className="online-dot" />{t("Processed on your computer")}<span>v{data.version}</span></div>
      </aside>
      <div className="workspace">
        <header><span>{t('Workspace')} <b>/</b> {categoryName(language, tool.category)}</span><div className="header-controls"><label className="language-picker">{t('Language')}<select aria-label={t('Language')} value={language} onChange={(event) => changeLanguage(event.target.value)}><option value="zh-TW">繁體中文</option><option value="en">English</option></select></label><span className={'status ' + (running ? 'running' : '')}><i />{t(status.key, status.values)}</span></div></header>
        <main onDragEnter={() => setDragging(true)} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }} onDrop={() => setDragging(false)}>
          <section className="hero"><div className="eyebrow">{categoryName(language, tool.category)}</div><h1>{tool.name}</h1><p>{tool.description}</p><code>{tool.module}</code></section>
          <section className="info-grid">
            <div><span>{t("When to use")}</span><p>{tool.purpose}</p></div>
            <div><span>{t("Inputs")}</span><p>{tool.inputs}</p></div>
            <div><span>{t("Outputs")}</span><p>{tool.outputs}</p></div>
          </section>
          {(tool.warning || !tool.builtin_requirements) && <div className="notice"><strong>{t("Before you run")}</strong><p>{tool.warning}{tool.warning && ' / '}{!tool.builtin_requirements && tool.requirements}</p></div>}
          {error && <div className="error" role="alert"><span>{errorText}</span><button aria-label={t("Close error message")} onClick={() => setError('')}><Icon name="close" /></button></div>}
          {(isDocument || dragging) && <section className={'drop-zone ' + (dragging ? 'dragging' : '')}><div className="drop-icon"><Icon name="arrow" size={25} /></div><div><strong>{t("Drop documents to convert")}</strong><p>PDF, XLSX, DOCX, PPTX, CSV, TXT <span>·</span> {t('Multiple files supported')}</p></div><button className="secondary" onClick={chooseDocuments}><Icon name="file" />{t("Choose documents")}</button></section>}
          {isDocument && <section className="card document-card">
            <div className="card-title"><h2>{t('Source documents')} <small>{files.length}</small></h2>{files.length > 0 && <button className="text-button" onClick={() => setFiles([])}>{t("Clear files")}</button>}</div>
            {files.length ? <ul className="file-list">{files.map((file) => <li key={file}><Icon name="file" /><div><strong>{file.split(/[\\/]/).pop()}</strong><span title={file}>{file}</span></div><button aria-label={t('Remove {file}', { file })} onClick={() => setFiles((current) => current.filter((value) => value !== file))}><Icon name="close" size={16} /></button></li>)}</ul> : <div className="empty-files">{t("Source files stay in place. Markdown is saved beside each source by default")}</div>}
            <div className="document-options">
              <label>{t("Output mode")}<select value={outputMode} onChange={(event) => { setOutputMode(event.target.value); setOutputPath('') }}><option value="source">{t("Save beside each source")}</option><option value="directory">{t("Save separately to a folder")}</option><option value="combine">{t("Combine into one Markdown file")}</option></select></label>
              <label className="check-label"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} />{t("Preview only, do not write files")}</label>
            </div>
            {outputMode !== 'source' && <div className="input-row"><input aria-label={t("Output location")} placeholder={t("Choose output location")} value={outputPath} onChange={(event) => setOutputPath(event.target.value)} /><button className="secondary" onClick={() => action(async () => { const value = outputMode === 'combine' ? await bridge().choose_save() : await bridge().choose_folder(); if (value) setOutputPath(value) })}><Icon name="folder" />{t("Browse")}</button></div>}
          </section>}
          <section className="card">
            <div className="card-title"><h2>{t("Run settings")}</h2>{data.defaults.bundled && !tool.source_only && <span className="badge">{t("Bundled runtime")}</span>}</div>
            <div className="settings-grid">
              <label>{t("Working directory")}<div className="input-row"><input value={cwd} onChange={(event) => setCwd(event.target.value)} /><button className="icon-button" aria-label={t("Choose working directory")} onClick={() => action(async () => { const value = await bridge().choose_folder(); if (value) setCwd(value) })}><Icon name="folder" /></button></div></label>
              {(!data.defaults.bundled || tool.source_only) && <label>{t("Development Python")}<div className="input-row"><input value={python} onChange={(event) => setPython(event.target.value)} placeholder={t("Choose Python executable")} /><button className="icon-button" aria-label={t("Choose Python")} onClick={() => action(async () => { const value = await bridge().choose_python(); if (value) setPython(value) })}><Icon name="folder" /></button></div></label>}
            </div>
            <details open={!isDocument} className="advanced">
              <summary>{t('CLI arguments and examples')} {isDocument && <span>{t("Advanced settings")}</span>}</summary>
              {isDocument && <label className="check-label"><input type="checkbox" checked={customArgs} onChange={(event) => setCustomArgs(event.target.checked)} />{t("Edit arguments manually, pause form synchronization")}</label>}
              <textarea aria-label={t("CLI arguments")} value={args} readOnly={isDocument && !customArgs} onChange={(event) => setArgs(event.target.value)} placeholder={t("Enter arguments, or view Help first")} />
              <div className="argument-actions"><button className="text-button" onClick={() => action(async () => { const values = await bridge().choose_files(false); setArgs(await bridge().append_paths(args, values)); if (isDocument) setCustomArgs(true) })}>{t("Add file paths")}</button><button className="text-button" onClick={() => action(async () => { const value = await bridge().choose_folder(); if (value) { setArgs(await bridge().append_paths(args, [value])); if (isDocument) setCustomArgs(true) } })}>{t("Add folder path")}</button><button className="text-button" onClick={() => { setArgs(tool.example_args); if (isDocument) setCustomArgs(true) }}>{t("Use example")}</button></div>
              <p className="example">{t("Example")} <code>{tool.example_args || t("View Help for details")}</code></p>
            </details>
          </section>
          <div className="actions"><button className="primary" disabled={busy || running} onClick={() => execute()}><Icon name="play" />{busy ? t("Starting...") : t("Run tool")}</button><button className="secondary" disabled={busy || running} onClick={() => execute(true)}>{t("View Help")}</button><button className="stop" disabled={!running} onClick={() => action(async () => { setStatus({ key: 'Stopping' }); const result = await bridge().stop_tool(run.run_id); setRun(result); setOutput(result.output); setStatus({ key: 'Stopped' }) })}>{t("Stop")}</button><span>{t("All files are processed locally")}</span></div>
          {running && <div className="progress" role="progressbar" aria-label={t("Tool running")}><i /></div>}
          <section className="card output-card"><div className="card-title"><h2><Icon name="terminal" />{t("Output")}</h2><div><button className="text-button" onClick={() => action(() => bridge().copy_text(output))}><Icon name="copy" size={15} />{t("Copy")}</button><button className="text-button" onClick={() => setOutput('')}>{t("Clear output")}</button></div></div><pre ref={outputRef}>{output ? (run?.output_truncated ? '[' + t('Earlier output was truncated') + ']\n' : '') + output : t('Ready. Results will appear here')}</pre><div className="input-row stdin"><input aria-label={t("Interactive input")} disabled={!running} value={stdin} onChange={(event) => setStdin(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') action(async () => { await bridge().send_input(run.run_id, stdin); setStdin('') }) }} placeholder={t("Enter a reply when the tool requests confirmation")} /><button className="secondary" disabled={!running || !stdin} onClick={() => action(async () => { await bridge().send_input(run.run_id, stdin); setStdin('') })}>{t("Send")}</button></div><details className="command"><summary>{t('View command')}{run && !running && <span>exit code {run.exit_code}</span>}</summary><code>{command}</code></details></section>
        </main>
      </div>
    </div>
  )
}

export default App
