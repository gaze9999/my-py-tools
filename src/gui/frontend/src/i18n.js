// English message keys are the fallback when a Traditional Chinese translation is missing.
export const zhTW = {
  "Confirm dropped files in the local file picker": "請在本機檔案選擇視窗確認拖入的來源文件",
  "Close web service": "停止網頁服務",
  "Stop the web service and any running tool?": "要停止網頁服務及執行中的工具嗎?",
  "Web service stopped": "網頁服務已停止",
  "Closing the browser tab does not stop the service. Use this button or Ctrl+C in the terminal": "關閉分頁不會停止服務, 請使用此按鈕或在終端機按 Ctrl+C",
  "This development tool requires a complete my-py-tools checkout and development Python": "此開發工具需要完整 my-py-tools 原始碼目錄與開發用 Python",
  "Choose a complete my-py-tools checkout as the working directory": "工作目錄需選擇完整的 my-py-tools 原始碼儲存庫",
  "Unable to copy output": "無法複製輸出",
  "Ready": "待命",
  "Local tool workspace": "本機工具工作台",
  "Search tools": "搜尋工具",
  "Search tools or use cases": "搜尋工具或用途",
  "Tool categories": "工具分類",
  "Categories by purpose": "用途分類",
  "Tools": "工具清單",
  "No matching tools": "沒有符合的工具",
  "Processed on your computer": "在你的電腦處理",
  "Workspace": "工作台",
  "When to use": "什麼時候用",
  "Inputs": "需要提供",
  "Outputs": "你會得到",
  "Before you run": "使用前確認",
  "Close error message": "關閉錯誤訊息",
  "Drop documents to convert": "拖曳文件, 開始轉換",
  "Multiple files supported": "支援多個檔案",
  "Choose documents": "選擇文件",
  "Source documents": "來源文件",
  "Clear files": "清空",
  "Remove {file}": "移除 {file}",
  "Source files stay in place. Markdown is saved beside each source by default": "文件會留在原位置, 轉換結果預設產生於來源旁",
  "Output mode": "輸出方式",
  "Save beside each source": "各自輸出至來源旁",
  "Save separately to a folder": "各自輸出至指定資料夾",
  "Combine into one Markdown file": "合併成一個 Markdown",
  "Preview only, do not write files": "只預覽, 不寫入檔案",
  "Output location": "輸出位置",
  "Choose output location": "選擇輸出位置",
  "Browse": "瀏覽",
  "Run settings": "執行設定",
  "Bundled runtime": "使用內建執行環境",
  "Working directory": "工作目錄",
  "Choose working directory": "選擇工作目錄",
  "Development Python": "開發用 Python",
  "Choose Python executable": "選擇 Python 執行檔",
  "Choose Python": "選擇 Python",
  "CLI arguments and examples": "CLI 參數與範例",
  "Advanced settings": "進階設定",
  "Edit arguments manually, pause form synchronization": "手動編輯參數, 暫停上方表單同步",
  "CLI arguments": "CLI 參數",
  "Enter arguments, or view Help first": "輸入參數, 或先查看 Help",
  "Add file paths": "加入檔案路徑",
  "Add folder path": "加入資料夾路徑",
  "Use example": "套用範例",
  "Example": "範例",
  "View Help for details": "請查看 Help",
  "Starting...": "啟動中...",
  "Run tool": "執行工具",
  "View Help": "查看 Help",
  "Stop": "停止",
  "All files are processed locally": "所有檔案都在本機處理",
  "Tool running": "工具執行中",
  "Output": "執行輸出",
  "Copy": "複製",
  "Clear output": "清除",
  "Ready. Results will appear here": "準備好了, 執行結果會顯示在這裡",
  "Interactive input": "互動輸入",
  "Enter a reply when the tool requests confirmation": "工具要求確認時, 在此輸入回覆",
  "Send": "送出",
  "View command": "檢視執行命令",
  "Preparing your tool workspace...": "正在準備你的工具工作台...",
  "Cannot connect to the desktop runtime. Restart the application": "無法連接桌面執行環境, 請重新啟動應用程式",
  "Choose or drop documents first": "請先選擇或拖入文件",
  "Choose an output location first": "請先選擇輸出位置",
  "Running": "執行中",
  "Completed": "執行完成",
  "Failed, exit code {code}": "執行失敗, exit code {code}",
  "Unable to retrieve results": "無法取得執行結果",
  "Failed to start": "啟動失敗",
  "Stopping": "停止中",
  "Stopped": "已停止",
  "Added {count} documents": "已加入 {count} 個文件",
  "Skipped unsupported or missing items: {paths}": "已略過不支援或不存在的項目: {paths}",
  "Earlier output was truncated": "較早輸出已截斷",
  "Language": "語言",
  "All": "全部",
  "Documents": "文件處理",
  "Maintenance": "維護",
  "Releases": "版本與發布",
  "Text": "文字",
  "Validation": "驗證"
}

export const LANGUAGE_KEY = 'my-py-tools.language'
export const LANGUAGES = ['zh-TW', 'en']

export function initialLanguage(storage) {
  try {
    const saved = storage?.getItem(LANGUAGE_KEY)
    return LANGUAGES.includes(saved) ? saved : 'zh-TW'
  } catch { return 'zh-TW' }
}

export function saveLanguage(storage, language) {
  try { storage?.setItem(LANGUAGE_KEY, language) } catch { /* Storage can be unavailable in native WebViews. */ }
}

export function translate(language, english, values = {}, dictionary = zhTW) {
  const message = language === 'zh-TW' && dictionary[english]?.trim() ? dictionary[english] : english
  return message.replace(/\{(\w+)\}/g, (match, key) => Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match)
}

export function categoryName(language, category) {
  const english = { '全部': 'All', '文件處理': 'Documents', '維護': 'Maintenance', '版本與發布': 'Releases', '文字': 'Text', '驗證': 'Validation' }[category] || category
  return translate(language, english)
}
