# Separate browser entry point, sharing the terminal launcher's runtime selection.
& (Join-Path $PSScriptRoot 'launch-cli.ps1') --web @args
exit $LASTEXITCODE
