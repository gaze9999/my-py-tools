# Start a desktop window in the background, without creating a console window.
$ErrorActionPreference = 'Stop'

function ConvertTo-NativeArgument([string] $Value) {
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

try {
    $executable = Join-Path $PSScriptRoot 'launch-gui.exe'
    $nativeArgs = @($args)
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        $runtimeArgs = @()
        $executable = Join-Path $PSScriptRoot '.venv-gui\Scripts\pythonw.exe'
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
            $command = Get-Command pythonw -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $command) {
                $command = Get-Command pyw -CommandType Application -ErrorAction Stop | Select-Object -First 1
                $runtimeArgs = @('-3')
            }
            $executable = $command.Source
        }
        $nativeArgs = $runtimeArgs + @((Join-Path $PSScriptRoot 'launch-gui.pyw')) + $nativeArgs
    }
    $argumentLine = ($nativeArgs | ForEach-Object { ConvertTo-NativeArgument ([string] $_) }) -join ' '
    $options = @{ FilePath = $executable; WorkingDirectory = $PSScriptRoot; WindowStyle = 'Hidden' }
    if ($argumentLine) { $options.ArgumentList = $argumentLine }
    Start-Process @options
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
