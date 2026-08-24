$ErrorActionPreference = 'Stop'
$project   = 'C:\Food\tamini'
$python    = 'C:\Food\venv\Scripts\python.exe'
$backupDir = Join-Path $project 'backups'
$keep      = 8

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmm'
$out   = Join-Path $backupDir "db_backup_$stamp.json"

Push-Location $project
try {
    & $python manage.py dumpdata --natural-primary --natural-foreign `
        --exclude contenttypes --exclude sessions `
        --exclude admin.logentry --exclude auth.permission `
        --output $out --indent 1
    if ($LASTEXITCODE -ne 0) { throw 'dumpdata failed' }

    Get-ChildItem $backupDir -Filter 'db_backup_*.json' |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $keep |
        Remove-Item -Force

    Write-Output ("Backup written: {0} ({1:N0} KB)" -f $out, ((Get-Item $out).Length / 1KB))
}
finally {
    Pop-Location
}
