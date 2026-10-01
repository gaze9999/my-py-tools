# Angular 與 Nx 工具

所有指令從 repository 根目錄執行; 未指定路徑選項時, `--root` 預設為目前目錄

## `angular/component_inventory.py`

遞迴掃描 Nx 工作區內的 `project.json`, Angular `@Component` 中繼資料與 `component-mapping.ts`; 支援 `apps/`, `libs/`, `packages/` 與自訂 project root, 並輸出元件所屬專案, class, selector, custom element, 程式檔, template, style, standalone 與簡短描述

```powershell
python -m angular.component_inventory customer --root C:\path\workspace
python -m angular.component_inventory --root C:\path\workspace --project transaction-ui --changed --json
python -m angular.component_inventory --root C:\path\workspace --limit 0
```

主要選項

- 位置查詢字可有多個, 必須全部出現在元件中繼資料或路徑內容
- `--project` 只保留專案名稱完全相符的結果, 不分大小寫
- `--changed` 比對 unstaged, staged 與 untracked 相關檔案, Git 查詢失敗時回傳錯誤
- `--json` 輸出可由程式讀取的 JSON
- `--limit 0` 不限制筆數, 負數回傳結束代碼 `2`

結束代碼 `0` 表示有結果, `1` 表示沒有相符元件, `2` 表示根目錄, Git 或參數錯誤

限制: 這是以 regex 為基礎的程式碼導覽清單, 不取代 TypeScript compiler 或 Angular template 分析; 動態中繼資料與非相對 import 可能無法解析

## `angular/form_contract_check.py`

依明確 JSON 欄位規格比對 TypeScript form control 宣告與 HTML `formControlName`, 不推測業務驗證規則

```powershell
python -m angular.form_contract_check --root C:\path\workspace --contract .\angular\contracts\forms.example.json
python -m angular.form_contract_check --root C:\path\workspace --contract .\contract.json --json
```

規格檔最外層必須是包含 `components` 陣列的物件, 每筆至少提供 `source`, 並可選擇提供 `template` 與 `controls`

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

檢查結果包含缺少程式檔, 缺少 template, 程式檔 control, template control, 或 template 有 control 但程式檔未偵測到; 結束代碼 `0` 表示沒有問題, `1` 表示發現問題, `2` 表示輸入或格式錯誤

## `angular/generator_preflight.py`

在執行 generator 前, 跨目錄搜尋預計使用的 identifier 或 selector 是否已存在

```powershell
python -m angular.generator_preflight --root C:\path\project --identifier SACRM190 --selector app-sacrm190
python -m angular.generator_preflight --root C:\path\project --identifier SACRM190 --allow-existing
```

掃描常見前端, 後端, 設定與文件文字格式, 包含 `.ts`, `.tsx`, `.js`, `.html`, `.scss`, `.json`, `.md`, `.yaml`, `.java`, `.kt`, `.graphql`, `.vue` 等; 跳過相依套件, build, Git 與 coverage 目錄, 空白 identifier 或 selector 會直接回傳參數錯誤

結束代碼 `0` 表示沒有衝突或已指定 `--allow-existing`, `1` 表示發現衝突, `2` 表示根目錄或讀取錯誤

## `angular/change_impact_report.py`

彙整 Git unstaged, staged 與 untracked 檔案, 並標示檔案內容中的 `selector:`, `@Input`, `@Output`, `CustomEvent`, `createCustomElement`, `component-mapping` 候選標記

```powershell
python -m angular.change_impact_report --root C:\path\repository
```

輸出固定為 JSON; Git 路徑使用 NUL 分隔讀取, 可保留中文與特殊字元檔名; 被標示的項目只代表需要進一步檢查, 不表示已確認有 breaking change 或 API 相容性問題

結束代碼 `0` 表示報告已產生, `2` 表示 Git 或檔案讀取錯誤
