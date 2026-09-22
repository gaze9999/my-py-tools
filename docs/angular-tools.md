# Angular 與 Nx 工具

所有指令從 repository 根目錄執行, path option 未指定時 `--root` 預設為目前目錄

## `angular/component_inventory.py`

掃描 Nx workspace 的 `apps/` 與 `libs/`, 讀取 `project.json`, Angular `@Component` metadata 與 `component-mapping.ts`, 輸出 component 所屬 project, class, selector, custom element, source, template, style, standalone 與簡短描述

```powershell
python -m angular.component_inventory customer --root C:\path\workspace
python -m angular.component_inventory --root C:\path\workspace --project transaction-ui --changed --json
python -m angular.component_inventory --root C:\path\workspace --limit 0
```

主要 option

- 位置查詢字可有多個, 必須全部出現在 component metadata 或路徑內容
- `--project` 只保留 project 名稱完全相符的結果, 不分大小寫
- `--changed` 比對 unstaged, staged 與 untracked companion files, Git 查詢失敗回傳錯誤
- `--json` 輸出 machine-readable JSON
- `--limit 0` 不限制筆數, 負數回傳 exit code `2`

exit code 為 `0` 表示有結果, `1` 表示沒有相符 component, `2` 表示 root、Git 或參數錯誤

限制: 這是 regex-based navigation inventory, 不取代 TypeScript compiler 或 Angular template analysis, dynamic metadata 與非相對 import 可能無法解析

## `angular/form_contract_check.py`

依明確 JSON contract 比對 TypeScript form control 宣告與 HTML `formControlName`, 不推測業務 validation

```powershell
python -m angular.form_contract_check --root C:\path\workspace --contract .\angular\contracts\forms.example.json
python -m angular.form_contract_check --root C:\path\workspace --contract .\contract.json --json
```

contract root 必須是含 `components` array 的 object, 每筆至少提供 `source`, 可選 `template` 與 `controls`

```json
{
  "components": [
    {
      "source": "apps/demo/src/demo.component.ts",
      "template": "apps/demo/src/demo.component.html",
      "controls": ["customerId"]
    }
  ]
}
```

findings 包含缺少 source, source control, template control, 或 template 有 control 但 source 未偵測到, exit code `0` 表示無 findings, `1` 表示有 findings, `2` 表示輸入或格式錯誤

## `angular/generator_preflight.py`

在執行 generator 前, 搜尋跨目錄是否已存在 proposed identifier 或 selector

```powershell
python -m angular.generator_preflight --root C:\path\project --identifier SACRM190 --selector app-sacrm190
python -m angular.generator_preflight --root C:\path\project --identifier SACRM190 --allow-existing
```

掃描 `.ts`, `.html`, `.scss`, `.css`, `.json`, `.xml`, `.properties`, 跳過 dependency, build, Git 與 coverage 目錄

exit code `0` 表示無 collision 或已指定 `--allow-existing`, `1` 表示發現 collision, `2` 表示 root 或讀取錯誤

## `angular/change_impact_report.py`

彙整 Git unstaged, staged 與 untracked 檔案, 並標示檔案內容中的 `selector:`, `@Input`, `@Output`, `CustomEvent`, `createCustomElement`, `component-mapping` 候選 marker

```powershell
python -m angular.change_impact_report --root C:\path\repository
```

輸出固定為 JSON, 被標示的 marker 只代表需要 review, 不代表已確認 breaking change 或 API 相容性

exit code `0` 表示 report 已產生, `2` 表示 Git 或檔案讀取錯誤
