// One interface, two transports. Browser sessions are authenticated by an HttpOnly cookie.
export function createBrowserBridge(host) {
  const invoke = async (name, values) => {
    const response = await host.fetch(`/api/${name}`, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-My-Py-Tools': '1' },
      body: JSON.stringify(values),
    })
    const result = await response.json()
    if (!response.ok) throw Object.assign(new Error(result.error || 'Unable to connect to the local web service'), { status: response.status })
    return result.value
  }
  const picker = async (method, values, multiple = false) => {
    try { return await invoke(method, values) }
    catch (error) {
      if (error.status !== 400) throw error
      const chinese = host.document.documentElement.lang !== 'en'
      const value = host.prompt(chinese
        ? '檔案選擇視窗不可用, 請輸入完整本機路徑, 多檔以換行分隔'
        : 'File picker unavailable. Enter full local paths, one per line')
      const paths = (value || '').split(/\r?\n/).map(path => path.trim().replace(/^"(.*)"$/, '$1')).filter(Boolean)
      return multiple ? paths : paths[0] || ''
    }
  }
  return new Proxy({}, {
    get: (_, name) => {
      if (name === 'choose_files') return (...values) => picker(name, values, true)
      if (['choose_folder', 'choose_python', 'choose_save'].includes(name)) return () => picker(name, [])
      if (name === 'copy_text') return async (value) => {
        if (host.navigator.clipboard) return host.navigator.clipboard.writeText(value)
        const element = host.document.createElement('textarea')
        element.value = value
        host.document.body.appendChild(element)
        try {
          element.select()
          if (!host.document.execCommand('copy')) throw new Error('Unable to copy output')
        } finally { element.remove() }
      }
      return (...values) => invoke(name, values)
    },
  })
}

let browserBridge
export function bridge() {
  if (!window.__MY_PY_TOOLS_BROWSER__) return window.pywebview.api
  return browserBridge ??= createBrowserBridge(window)
}

export function bridgeReady() {
  return Boolean(window.__MY_PY_TOOLS_BROWSER__ || window.pywebview?.api)
}
