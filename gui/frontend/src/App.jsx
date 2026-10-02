import { useCallback, useEffect, useRef, useState } from 'react'

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
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
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
  const [status, setStatus] = useState('待命')
  const [output, setOutput] = useState('')
  const [stdin, setStdin] = useState('')
  const [dragging, setDragging] = useState(false)
  const [customArgs, setCustomArgs] = useState(false)
  const [command, setCommand] = useState('')
  const outputRef = useRef(null)
  const filesRef = useRef([])
  const running = Boolean(run?.running)
  const tool = data?.tools.find((item) => item.id === toolId)
  const isDocument = toolId === 'document-to-markdown'
  const visible = (data?.tools || []).filter((item) =>
    (category === '全部' || category === item.category) &&
    [item.name, item.module, item.description, item.purpose].join(' ').toLowerCase().includes(query.trim().toLowerCase()),
  )

  useEffect(() => {
    let disposed = false
    const initialize = async () => {
      try {
        const result = await bridge().bootstrap()
        if (disposed) return
        setData(result)
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
      if (!window.pywebview?.api) setError('無法連接桌面執行環境, 請重新啟動應用程式')
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
        setStatus('已加入 ' + result.accepted.length + ' 個文件')
      }
      setError(result.rejected.length ? '已略過不支援或不存在的項目: ' + result.rejected.join(', ') : '')
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
        setOutput((result.output_truncated ? '[較早輸出已截斷]\n' : '') + result.output)
        if (result.running) timer = setTimeout(poll, 300)
        else setStatus(result.exit_code === 0 ? '執行完成' : '執行失敗, exit code ' + result.exit_code)
      } catch (failure) {
        if (!disposed) { setError(String(failure.message || failure)); setStatus('無法取得執行結果') }
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
        throw new Error(!files.length ? '請先選擇或拖入文件' : '請先選擇輸出位置')
      }
      const result = await bridge().start_tool(toolId, help ? '--help' : args, cwd, python)
      setOutput(result.output)
      setRun(result)
      setStatus('執行中')
    } catch (failure) { setError(String(failure.message || failure)); setStatus('啟動失敗') }
    finally { setBusy(false) }
  }

  if (!data || !tool) return <div className="loading"><div className="brand-mark"><Icon name="tools" size={30} /></div><h1>My Py Tools</h1><p>{error || '正在準備你的工具工作台...'}</p></div>

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Icon name="tools" size={23} /></div><div><strong>My Py Tools</strong><span>本機工具工作台</span></div></div>
        <div className="search"><Icon name="search" /><input aria-label="搜尋工具" placeholder="搜尋工具或用途" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <div className="section-label">工具分類 <span>{data.tools.length}</span></div>
        <nav aria-label="用途分類">{['全部', ...data.categories].map((item) => <button key={item} onClick={() => selectCategory(item)} className={category === item ? 'active' : ''}><span>{item}</span><small>{item === '全部' ? data.tools.length : data.tools.filter((entry) => entry.category === item).length}</small></button>)}</nav>
        <div className="section-label">工具清單</div>
        <div className="tool-list">{visible.length ? visible.map((item) => <button key={item.id} className={toolId === item.id ? 'selected' : ''} onClick={() => selectTool(item)}><strong>{item.name}</strong><span>{item.description}</span></button>) : <p className="empty">沒有符合的工具</p>}</div>
        <div className="sidebar-footer"><span className="online-dot" />在你的電腦處理<span>v{data.version}</span></div>
      </aside>
      <div className="workspace">
        <header><span>工作台 <b>/</b> {tool.category}</span><span className={'status ' + (running ? 'running' : '')}><i />{status}</span></header>
        <main onDragEnter={() => setDragging(true)} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }} onDrop={() => setDragging(false)}>
          <section className="hero"><div className="eyebrow">{tool.category}</div><h1>{tool.name}</h1><p>{tool.description}</p><code>{tool.module}</code></section>
          <section className="info-grid">
            <div><span>什麼時候用</span><p>{tool.purpose}</p></div>
            <div><span>需要提供</span><p>{tool.inputs}</p></div>
            <div><span>你會得到</span><p>{tool.outputs}</p></div>
          </section>
          {(tool.warning || tool.requirements !== '使用內建 Python 核心') && <div className="notice"><strong>使用前確認</strong><p>{tool.warning}{tool.warning && ' / '}{tool.requirements !== '使用內建 Python 核心' && tool.requirements}</p></div>}
          {error && <div className="error" role="alert"><span>{error}</span><button aria-label="關閉錯誤訊息" onClick={() => setError('')}><Icon name="close" /></button></div>}
          {(isDocument || dragging) && <section className={'drop-zone ' + (dragging ? 'dragging' : '')}><div className="drop-icon"><Icon name="arrow" size={25} /></div><div><strong>拖曳文件, 開始轉換</strong><p>PDF, XLSX, DOCX, PPTX, CSV, TXT <span>·</span> 支援多個檔案</p></div><button className="secondary" onClick={chooseDocuments}><Icon name="file" />選擇文件</button></section>}
          {isDocument && <section className="card document-card">
            <div className="card-title"><h2>來源文件 <small>{files.length}</small></h2>{files.length > 0 && <button className="text-button" onClick={() => setFiles([])}>清空</button>}</div>
            {files.length ? <ul className="file-list">{files.map((file) => <li key={file}><Icon name="file" /><div><strong>{file.split(/[\\/]/).pop()}</strong><span title={file}>{file}</span></div><button aria-label={'移除 ' + file} onClick={() => setFiles((current) => current.filter((value) => value !== file))}><Icon name="close" size={16} /></button></li>)}</ul> : <div className="empty-files">文件會留在原位置, 轉換結果預設產生於來源旁</div>}
            <div className="document-options">
              <label>輸出方式<select value={outputMode} onChange={(event) => { setOutputMode(event.target.value); setOutputPath('') }}><option value="source">各自輸出至來源旁</option><option value="directory">各自輸出至指定資料夾</option><option value="combine">合併成一個 Markdown</option></select></label>
              <label className="check-label"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} />只預覽, 不寫入檔案</label>
            </div>
            {outputMode !== 'source' && <div className="input-row"><input aria-label="輸出位置" placeholder="選擇輸出位置" value={outputPath} onChange={(event) => setOutputPath(event.target.value)} /><button className="secondary" onClick={() => action(async () => { const value = outputMode === 'combine' ? await bridge().choose_save() : await bridge().choose_folder(); if (value) setOutputPath(value) })}><Icon name="folder" />瀏覽</button></div>}
          </section>}
          <section className="card">
            <div className="card-title"><h2>執行設定</h2>{data.defaults.bundled && !tool.source_only && <span className="badge">使用內建執行環境</span>}</div>
            <div className="settings-grid">
              <label>工作目錄<div className="input-row"><input value={cwd} onChange={(event) => setCwd(event.target.value)} /><button className="icon-button" aria-label="選擇工作目錄" onClick={() => action(async () => { const value = await bridge().choose_folder(); if (value) setCwd(value) })}><Icon name="folder" /></button></div></label>
              {(!data.defaults.bundled || tool.source_only) && <label>開發用 Python<div className="input-row"><input value={python} onChange={(event) => setPython(event.target.value)} placeholder="選擇 Python 執行檔" /><button className="icon-button" aria-label="選擇 Python" onClick={() => action(async () => { const value = await bridge().choose_python(); if (value) setPython(value) })}><Icon name="folder" /></button></div></label>}
            </div>
            <details open={!isDocument} className="advanced">
              <summary>CLI 參數與範例 {isDocument && <span>進階設定</span>}</summary>
              {isDocument && <label className="check-label"><input type="checkbox" checked={customArgs} onChange={(event) => setCustomArgs(event.target.checked)} />手動編輯參數, 暫停上方表單同步</label>}
              <textarea aria-label="CLI 參數" value={args} readOnly={isDocument && !customArgs} onChange={(event) => setArgs(event.target.value)} placeholder="輸入參數, 或先查看 Help" />
              <div className="argument-actions"><button className="text-button" onClick={() => action(async () => { const values = await bridge().choose_files(false); setArgs(await bridge().append_paths(args, values)); if (isDocument) setCustomArgs(true) })}>加入檔案路徑</button><button className="text-button" onClick={() => action(async () => { const value = await bridge().choose_folder(); if (value) { setArgs(await bridge().append_paths(args, [value])); if (isDocument) setCustomArgs(true) } })}>加入資料夾路徑</button><button className="text-button" onClick={() => { setArgs(tool.example_args); if (isDocument) setCustomArgs(true) }}>套用範例</button></div>
              <p className="example">範例 <code>{tool.example_args || '請查看 Help'}</code></p>
            </details>
          </section>
          <div className="actions"><button className="primary" disabled={busy || running} onClick={() => execute()}><Icon name="play" />{busy ? '啟動中...' : '執行工具'}</button><button className="secondary" disabled={busy || running} onClick={() => execute(true)}>查看 Help</button><button className="stop" disabled={!running} onClick={() => action(async () => { setStatus('停止中'); const result = await bridge().stop_tool(run.run_id); setRun(result); setOutput(result.output); setStatus('已停止') })}>停止</button><span>所有檔案都在本機處理</span></div>
          {running && <div className="progress" role="progressbar" aria-label="工具執行中"><i /></div>}
          <section className="card output-card"><div className="card-title"><h2><Icon name="terminal" />執行輸出</h2><div><button className="text-button" onClick={() => action(() => bridge().copy_text(output))}><Icon name="copy" size={15} />複製</button><button className="text-button" onClick={() => setOutput('')}>清除</button></div></div><pre ref={outputRef}>{output || '準備好了, 執行結果會顯示在這裡'}</pre><div className="input-row stdin"><input aria-label="互動輸入" disabled={!running} value={stdin} onChange={(event) => setStdin(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') action(async () => { await bridge().send_input(run.run_id, stdin); setStdin('') }) }} placeholder="工具要求確認時, 在此輸入回覆" /><button className="secondary" disabled={!running || !stdin} onClick={() => action(async () => { await bridge().send_input(run.run_id, stdin); setStdin('') })}>送出</button></div><details className="command"><summary>檢視執行命令{run && !running && <span>exit code {run.exit_code}</span>}</summary><code>{command}</code></details></section>
        </main>
      </div>
    </div>
  )
}

export default App
