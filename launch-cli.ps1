# Windows PowerShell 5.1 / PowerShell 7. Preserve caller cwd and native exit code.
$ErrorActionPreference = 'Stop'

function ConvertTo-NativeArgument([string] $Value) {
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

try {
    $executable = Join-Path $PSScriptRoot 'launch-cli.exe'
    $nativeArgs = @($args)
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        $executable = Join-Path $PSScriptRoot '.venv-gui\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
            $executable = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        }
        $nativeArgs = @((Join-Path $PSScriptRoot 'launch-cli.py')) + $nativeArgs
    }
    $argumentLine = ($nativeArgs | ForEach-Object { ConvertTo-NativeArgument ([string] $_) }) -join ' '
    $options = @{ FilePath = $executable; WorkingDirectory = (Get-Location).ProviderPath; NoNewWindow = $true; Wait = $true; PassThru = $true }
    if ($argumentLine) { $options.ArgumentList = $argumentLine }
    $process = Start-Process @options
    exit $process.ExitCode
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
