// Built-in English metadata. New tools can provide translations in Python ToolSpec.
export const englishTools = {
  "component-inventory": {
    "name": "Component inventory",
    "description": "List Angular components, selectors, templates, styles and custom elements in an Nx workspace",
    "purpose": "Understand component locations and public identifiers before taking over or reorganizing an Angular/Nx project",
    "inputs": "Nx or Angular workspace root",
    "outputs": "Component and selector inventory, with optional JSON output"
  },
  "form-contract-check": {
    "name": "Form field specification check",
    "description": "Compare TypeScript form controls and HTML formControlName against a JSON field specification",
    "purpose": "Check that TypeScript and HTML match the documented field specification before changing a form",
    "inputs": "Project root and a JSON field specification",
    "outputs": "Missing, extra or inconsistent form controls and formControlName references"
  },
  "generator-preflight": {
    "name": "Generator preflight",
    "description": "Find identifier and selector conflicts before generating files",
    "purpose": "Avoid duplicate identifiers, selectors and filenames before running a generator",
    "inputs": "Project root and the proposed identifier or selector",
    "outputs": "Conflict candidates and source locations, without changing project files"
  },
  "change-impact-report": {
    "name": "Git change impact report",
    "description": "Summarize staged, unstaged and untracked files and public-interface candidates",
    "purpose": "Review the potential public-interface impact of Git changes before review or commit",
    "inputs": "Git repository root",
    "outputs": "Changed files and public-interface candidates",
    "requirements": "Git and a Git repository are required"
  },
  "document-to-markdown": {
    "name": "Documents to Markdown",
    "description": "Convert PDF, XLSX, DOCX, PPTX, CSV or TXT into searchable Markdown",
    "purpose": "Make documents searchable and easy to compare or use with other tools",
    "inputs": "One or more supported documents, selected or dropped",
    "outputs": "Same-name .md files beside each source by default, with source information and extraction time to the second",
    "warning": "Normal mode may create or replace Markdown files. Preview with --dry-run or compare with --check"
  },
  "field-matrix": {
    "name": "Field specification matrix",
    "description": "Extract a field specification matrix from converted Markdown tables",
    "purpose": "Organize field names, types and descriptions for specification review",
    "inputs": "A Markdown extract containing tables and an output path",
    "outputs": "A field specification matrix in Markdown"
  },
  "locate-markdown-extracts": {
    "name": "Locate Markdown extracts",
    "description": "Find current, stale and candidate Markdown extracts by source path and SHA-256",
    "purpose": "Identify current and outdated extracts when multiple Markdown versions exist",
    "inputs": "Original document and a Markdown search root",
    "outputs": "Candidates classified by source metadata and SHA-256"
  },
  "markdown-guard": {
    "name": "Guarded Markdown update",
    "description": "Protect updates with SHA-256, dry-run, atomic replacement and readback verification",
    "purpose": "Update a selected Markdown range while detecting concurrent file changes",
    "inputs": "Target Markdown, operation, content and optional expected SHA-256",
    "outputs": "Preview or guarded update, verified after writing",
    "warning": "Only --write updates the target. --in-place is a fallback mode that creates a backup first"
  },
  "markdown-diff": {
    "name": "Markdown structure diff",
    "description": "Compare Markdown headings, list items, table rows and SHA-256",
    "purpose": "Inspect structural differences without being distracted by whitespace or layout",
    "inputs": "Before and after Markdown files",
    "outputs": "Heading, list, table and SHA-256 differences"
  },
  "cleanup-artifacts": {
    "name": "Clean development artifacts",
    "description": "Preview or quarantine caches and build artifacts, and manage the quarantine",
    "purpose": "Preview caches and intermediate files before cleanup to reduce accidental deletion",
    "inputs": "Project root and optional scope",
    "outputs": "Preview, quarantine or quarantine-cleanup results",
    "warning": "Preview is the default. --apply moves files. --purge-quarantine permanently deletes old quarantine runs"
  },
  "rewrite-git-history": {
    "name": "Rewrite Git history identity",
    "description": "Change authors and committers across all refs to the repository-local identity",
    "purpose": "Correct history identity only when a full history rewrite is explicitly intended",
    "inputs": "Git repository and repository-local identity settings",
    "outputs": "Backup bundle and rewritten refs, with REWRITE confirmation",
    "requirements": "Git and repository-local user.name and user.email are required",
    "warning": "Destructive history rewrite. Creates a bundle and requires REWRITE through stdin"
  },
  "environment-consistency": {
    "name": "Environment consistency check",
    "description": "Read-only comparison of paths, sizes and SHA-256 across Skills, runtime or mirror folders",
    "purpose": "Check two environment trees without synchronizing them",
    "inputs": "Source and target folders",
    "outputs": "Path, size and SHA-256 differences"
  },
  "tokenizer": {
    "name": "Token count",
    "description": "Count with tiktoken, falling back to a character-ratio estimate",
    "purpose": "Estimate token usage for prompts, documents or API payloads",
    "inputs": "Text, file or stdin, with an optional encoding",
    "outputs": "Character and token counts, with an explicit fallback label when estimation is used"
  },
  "validation-index": {
    "name": "Validation evidence index",
    "description": "Index run-*/results.json without rerunning builds or tests",
    "purpose": "Find which recorded checks passed and which remain unverified",
    "inputs": "Folder containing validation runs",
    "outputs": "Commands, results, source baselines and unverified items"
  },
  "prepare-release": {
    "name": "Prepare release assets",
    "description": "Build the source ZIP, two independent core wheels and a SHA-256 manifest",
    "purpose": "Prepare verifiable release assets before publishing",
    "inputs": "Complete my-py-tools checkout, version and optional output folder",
    "outputs": "Release assets and SHA-256 manifest",
    "requirements": "Complete source checkout, development Python, pip, setuptools and wheel are required",
    "warning": "Without --dry-run, writes dist/<tag>. Does not commit, push or create a release"
  },
  "release": {
    "name": "Validate and publish release",
    "description": "Validate source, prepare assets or publish after explicit confirmation",
    "purpose": "Verify prepared assets and publish a GitHub Release after review",
    "inputs": "Clean, committed checkout, tag and authenticated GitHub CLI",
    "outputs": "Validation results or a published release, which changes remote state",
    "requirements": "Complete source checkout, development Python, Git and authenticated GitHub CLI are required",
    "warning": "publish pushes the current branch and creates a release. Review the diff and confirm the full tag first"
  }
}

const fields = ['name', 'description', 'purpose', 'inputs', 'outputs', 'requirements', 'warning']

export function localizeTool(language, tool) {
  const english = {
    name: tool.module.split('.').pop().replaceAll('_', ' '),
    description: 'Run ' + tool.module,
    purpose: 'Run this command using the arguments described in Help',
    inputs: 'Files, folders or text, depending on the CLI arguments',
    outputs: 'Results appear in the output panel. File writes depend on CLI arguments',
    requirements: tool.source_only ? 'Requires the complete source checkout and development Python' : 'Uses the bundled Python core',
    warning: tool.warning ? 'Review Help and preview the operation before running' : '',
    ...Object.fromEntries(fields.filter(field => typeof tool[field] === 'string' && !/[\u3400-\u9fff]/u.test(tool[field]) && tool[field].trim()).map(field => [field, tool[field]])),
    ...englishTools[tool.id],
    ...tool.translations?.en,
  }
  // Existing catalog fields are Traditional Chinese. Explicit locale maps use English per missing field.
  const chinese = tool.translations?.['zh-TW'] ?? tool
  const localized = { ...tool }
  for (const field of fields) {
    localized[field] = language === 'zh-TW' && chinese[field]?.trim() ? chinese[field] : english[field]
  }
  localized.builtin_requirements = !tool.source_only && (!tool.requirements || tool.requirements === '使用內建 Python 核心')
  localized.search_text = fields.map(field => [tool[field], english[field], chinese[field]].join(' ')).join(' ')
  return localized
}
