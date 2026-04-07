$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$zipPath = Join-Path $repo "gen_dieu_tin_for_testers.zip"
$stage = Join-Path $env:TEMP ("gen_dieu_tin_zip_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    & robocopy.exe $repo $stage /E /XD .venv .git __pycache__ .cursor /NFL /NDL /NJH /NJS /NP | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy failed (exit $rc)"
    }
    if (Test-Path $zipPath) {
        Remove-Item -Force $zipPath
    }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath -Force
    Write-Host "Created: $zipPath"
}
finally {
    if (Test-Path $stage) {
        Remove-Item -Recurse -Force $stage
    }
}
