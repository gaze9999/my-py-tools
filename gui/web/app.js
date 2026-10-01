const token = new URLSearchParams(window.location.search).get("token") || "";
const state = { tools: [], selected: null, category: "全部", runId: null, poller: null, picker: null };

const byId = (id) => document.getElementById(id);
const elements = {
  status: byId("status"), appVersion: byId("appVersion"), toolSearch: byId("toolSearch"), categoryTabs: byId("categoryTabs"), toolList: byId("toolList"),
  toolCategory: byId("toolCategory"), toolName: byId("toolName"), toolDescription: byId("toolDescription"),
  toolModule: byId("toolModule"), toolWarning: byId("toolWarning"), pythonPath: byId("pythonPath"),
  cwd: byId("cwd"), arguments: byId("arguments"), exampleArgs: byId("exampleArgs"),
  commandPreview: byId("commandPreview"), output: byId("output"), exitCode: byId("exitCode"),
  runTool: byId("runTool"), runHelp: byId("runHelp"), stopTool: byId("stopTool"),
  stdinValue: byId("stdinValue"), sendInput: byId("sendInput"), pathDialog: byId("pathDialog"),
  progressTrack: byId("progressTrack"),
  dialogTitle: byId("dialogTitle"), pathLocation: byId("pathLocation"), pathEntries: byId("pathEntries"),
  parentPath: byId("parentPath"), chooseCurrent: byId("chooseCurrent"), pathNotice: byId("pathNotice"),
};

async function api(path, options = {}) {
  const separator = path.includes("?") ? "&" : "?";
  const retries = (options.method || "GET").toUpperCase() === "GET" ? 2 : 0;
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(`${path}${separator}token=${encodeURIComponent(token)}`, {
        ...options,
        headers: { "Content-Type": "application/json", "X-GUI-Token": token, ...(options.headers || {}) },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload;
    } catch (error) {
      lastError = error;
      if (attempt < retries) await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
  throw lastError;
}

function setStatus(text, kind = "idle") {
  elements.status.textContent = text;
  elements.status.className = `status ${kind}`;
}

function quoteArg(value) {
  if (!value) return '""';
  return `"${value.replaceAll('"', '\\"')}"`;
}

function preview() {
  if (!state.selected) return;
  const parts = [quoteArg(elements.pythonPath.value), "-u", "-m", state.selected.module];
  if (elements.arguments.value.trim()) parts.push(elements.arguments.value.trim());
  elements.commandPreview.textContent = parts.join(" ");
}

function renderCategories() {
  const categories = ["全部", ...new Set(state.tools.map((tool) => tool.category))];
  elements.categoryTabs.replaceChildren();
  for (const category of categories) {
    const button = document.createElement("button");
    button.type = "button";
    button.role = "tab";
    button.className = `category-tab${state.category === category ? " active" : ""}`;
    button.textContent = category;
    button.setAttribute("aria-selected", String(state.category === category));
    button.addEventListener("click", () => {
      state.category = category;
      renderCategories();
      renderTools();
    });
    elements.categoryTabs.append(button);
  }
}

function renderTools() {
  const query = elements.toolSearch.value.trim().toLocaleLowerCase();
  elements.toolList.replaceChildren();
  for (const tool of state.tools.filter((item) =>
    (state.category === "全部" || item.category === state.category) &&
    `${item.name} ${item.category} ${item.module} ${item.description}`.toLocaleLowerCase().includes(query))) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tool-card${state.selected?.id === tool.id ? " active" : ""}`;
    const name = document.createElement("strong");
    name.textContent = tool.name;
    const module = document.createElement("small");
    module.textContent = tool.module;
    button.append(name, module);
    button.addEventListener("click", () => selectTool(tool));
    elements.toolList.append(button);
  }
}

function selectTool(tool) {
  state.selected = tool;
  elements.toolCategory.textContent = tool.category;
  elements.toolName.textContent = tool.name;
  elements.toolDescription.textContent = tool.description;
  elements.toolModule.textContent = tool.module;
  elements.exampleArgs.textContent = tool.example_args || "不需要參數";
  elements.toolWarning.hidden = !tool.warning;
  elements.toolWarning.textContent = tool.warning;
  renderTools();
  preview();
}

function setRunning(running) {
  elements.runTool.disabled = running;
  elements.runHelp.disabled = running;
  elements.stopTool.disabled = !running;
  elements.stdinValue.disabled = !running;
  elements.sendInput.disabled = !running;
  elements.progressTrack.hidden = !running;
}

async function startRun(argsOverride = null) {
  if (!state.selected) return;
  elements.output.textContent = "";
  elements.exitCode.textContent = "";
  try {
    const result = await api("/api/run", {
      method: "POST",
      body: JSON.stringify({
        tool_id: state.selected.id,
        args: argsOverride ?? elements.arguments.value,
        cwd: elements.cwd.value,
        python: elements.pythonPath.value,
      }),
    });
    state.runId = result.run_id;
    setRunning(true);
    setStatus("執行中", "running");
    updateRun(result);
    clearInterval(state.poller);
    state.poller = setInterval(pollRun, 350);
  } catch (error) {
    elements.output.textContent = `error: ${error.message}`;
    setStatus("啟動失敗", "failed");
  }
}

function updateRun(result) {
  const nearBottom = elements.output.scrollHeight - elements.output.scrollTop - elements.output.clientHeight < 80;
  elements.output.textContent = result.output || "";
  if (result.output_truncated) elements.output.textContent = `[較早輸出已截斷]\n${elements.output.textContent}`;
  if (nearBottom) elements.output.scrollTop = elements.output.scrollHeight;
  if (!result.running && result.run_id) {
    clearInterval(state.poller);
    state.poller = null;
    setRunning(false);
    elements.exitCode.textContent = `exit code ${result.exit_code}`;
    setStatus(result.exit_code === 0 ? "完成" : "執行失敗", result.exit_code === 0 ? "success" : "failed");
  }
}

async function pollRun() {
  if (!state.runId) return;
  try {
    updateRun(await api(`/api/status?run_id=${encodeURIComponent(state.runId)}`));
  } catch (error) {
    clearInterval(state.poller);
    state.poller = null;
    setRunning(false);
    setStatus("連線中斷", "failed");
  }
}

async function stopRun() {
  if (!state.runId) return;
  try {
    updateRun(await api("/api/stop", { method: "POST", body: JSON.stringify({ run_id: state.runId }) }));
  } catch (error) {
    elements.output.textContent += `\nerror: ${error.message}`;
  }
}

async function sendInput() {
  if (!state.runId || !elements.stdinValue.value) return;
  try {
    await api("/api/input", {
      method: "POST",
      body: JSON.stringify({ run_id: state.runId, value: elements.stdinValue.value }),
    });
    elements.stdinValue.value = "";
  } catch (error) {
    elements.output.textContent += `\nerror: ${error.message}`;
  }
}

async function openPicker(mode, target) {
  state.picker = { mode, target, parent: null };
  elements.dialogTitle.textContent = mode === "file" ? "選擇檔案" : "選擇資料夾";
  elements.chooseCurrent.hidden = mode === "file";
  elements.pathDialog.showModal();
  await loadPath(target === "cwd" ? elements.cwd.value : elements.pathLocation.value || elements.cwd.value);
}

async function loadPath(path) {
  elements.pathNotice.textContent = "讀取中";
  try {
    const result = await api(`/api/files?path=${encodeURIComponent(path || "")}`);
    elements.pathLocation.value = result.path;
    state.picker.parent = result.parent;
    elements.parentPath.disabled = !result.parent;
    elements.pathEntries.replaceChildren();
    for (const entry of result.entries) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "path-entry";
      const name = document.createElement("span");
      name.textContent = `${entry.is_directory ? "📁" : "📄"} ${entry.name}`;
      const action = document.createElement("small");
      action.textContent = entry.is_directory ? "開啟" : "選取";
      button.append(name, action);
      button.addEventListener("click", () => {
        if (entry.is_directory) loadPath(entry.path);
        else if (state.picker.mode === "file") choosePath(entry.path);
      });
      elements.pathEntries.append(button);
    }
    elements.pathNotice.textContent = result.truncated ? "只顯示前 500 筆" : `${result.entries.length} 筆`;
  } catch (error) {
    elements.pathNotice.textContent = `error: ${error.message}`;
  }
}

function choosePath(path) {
  const target = state.picker?.target;
  if (target === "python") elements.pythonPath.value = path;
  else if (target === "cwd") elements.cwd.value = path;
  else if (target === "args") {
    const prefix = elements.arguments.value.trim();
    elements.arguments.value = `${prefix}${prefix ? " " : ""}${quoteArg(path)}`;
  }
  elements.pathDialog.close();
  preview();
}

async function initialize() {
  try {
    const data = await api("/api/tools");
    elements.appVersion.textContent = data.version ? `v${data.version}` : "";
    state.tools = data.tools;
    elements.pythonPath.value = data.defaults.python;
    elements.cwd.value = data.defaults.cwd;
    const initialTool = state.tools.find((tool) => tool.id === data.defaults.tool_id) || state.tools[0];
    renderCategories();
    selectTool(initialTool);
    if (data.defaults.args) elements.arguments.value = data.defaults.args;
    preview();
    if (data.discovery_warnings?.length) {
      elements.output.textContent = `部分工具無法載入:\n${data.discovery_warnings.join("\n")}`;
      setStatus("部分工具未載入", "failed");
    } else {
      setStatus("待命", "idle");
    }
  } catch (error) {
    elements.output.textContent = `GUI 初始化失敗: ${error.message}\n請查看 .gui/my-py-tools-gui.log`;
    setStatus("初始化失敗", "failed");
  }
}

elements.toolSearch.addEventListener("input", renderTools);
elements.pythonPath.addEventListener("input", preview);
elements.arguments.addEventListener("input", preview);
byId("applyExample").addEventListener("click", () => { elements.arguments.value = state.selected?.example_args || ""; preview(); });
byId("browsePython").addEventListener("click", () => openPicker("file", "python"));
byId("browseCwd").addEventListener("click", () => openPicker("directory", "cwd"));
byId("addFile").addEventListener("click", () => openPicker("file", "args"));
byId("addDirectory").addEventListener("click", () => openPicker("directory", "args"));
elements.runTool.addEventListener("click", () => startRun());
elements.runHelp.addEventListener("click", () => startRun("--help"));
elements.stopTool.addEventListener("click", stopRun);
elements.sendInput.addEventListener("click", sendInput);
elements.stdinValue.addEventListener("keydown", (event) => { if (event.key === "Enter") sendInput(); });
byId("clearOutput").addEventListener("click", () => { elements.output.textContent = ""; elements.exitCode.textContent = ""; });
byId("copyOutput").addEventListener("click", () => navigator.clipboard.writeText(elements.output.textContent));
byId("refreshPath").addEventListener("click", () => loadPath(elements.pathLocation.value));
elements.parentPath.addEventListener("click", () => state.picker?.parent && loadPath(state.picker.parent));
elements.chooseCurrent.addEventListener("click", () => choosePath(elements.pathLocation.value));
byId("closeGui").addEventListener("click", async () => {
  if (!window.confirm("關閉 GUI 並停止目前執行中的工具?")) return;
  try { await api("/api/shutdown", { method: "POST", body: "{}" }); } catch (_) { /* server may close first */ }
  setRunning(false);
  setStatus("已關閉", "idle");
  elements.output.textContent += "\nGUI server 已關閉, 可關閉此分頁";
});

initialize();
