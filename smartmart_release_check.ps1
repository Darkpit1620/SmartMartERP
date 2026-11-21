# SmartMart ERP - Final development/GitHub readiness checker
# Read-only diagnostics except the verified private backup saved OUTSIDE this repo.
# This script DOES NOT stage, commit or push Git changes.
param(
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Run-Step {
    param([string]$Title, [string]$Program, [string[]]$Arguments)
    Write-Host "`n=== $Title ===" -ForegroundColor Cyan
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed (exit code $LASTEXITCODE). Nothing was pushed to GitHub."
    }
}

try {
    Write-Host "SMARTMART ERP - FINAL DEVELOPMENT RELEASE CHECK" -ForegroundColor Green
    if (-not (Test-Path -LiteralPath 'manage.py' -PathType Leaf)) {
        throw 'manage.py not found. Extract this pack directly into the SmartMartERP project root.'
    }
    if (-not (Test-Path -LiteralPath 'smartmart_backup.py' -PathType Leaf)) {
        throw 'smartmart_backup.py missing. The checker requires a verified private backup.'
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python not found. Activate your existing .venv before running this script.'
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git not found in PATH.'
    }
    Run-Step 'Verify project is a Git repository' 'git' @('rev-parse','--is-inside-work-tree')
    Run-Step 'Back up private database and media outside the Git project' 'python' @('smartmart_backup.py')
    Run-Step 'Django system checks' 'python' @('manage.py','check')
    Run-Step 'Check for missing migration files (makes no migrations)' 'python' @('manage.py','makemigrations','--check','--dry-run')
    if (-not $SkipTests) {
        Run-Step 'Full Django test suite (temporary test database)' 'python' @('manage.py','test','--noinput')
    } else {
        Write-Warning 'Full tests skipped; do not treat this as final release verification.'
    }
    Run-Step 'Read-only operations audit' 'python' @('manage.py','smartmart_audit')

    Write-Host "`n=== Secret / private-file tracking check ===" -ForegroundColor Cyan
    $tracked = @(& git -c core.quotePath=false ls-files)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate tracked Git files.' }
    $untracked = @(& git -c core.quotePath=false ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate untracked Git files.' }
    $candidates = @($tracked) + @($untracked)
    $sensitive = @()
    foreach ($raw in $candidates) {
        $path = ([string]$raw).Trim('"') -replace '\\','/'
        if ($path -match '(?i)(^|/)(\.venv|venv|__pycache__|media|uploads|SmartMartERP_Backups)(/|$)' -or
            $path -match '(?i)(^|/)(\.env($|\.)|local_secret\.py$|db\.sqlite3$|[^/]*\.sqlite3$|[^/]*\.sqlite$|[^/]*\.pem$|[^/]*\.pfx$|[^/]*\.p12$|id_rsa$)' -or
            $path -match '(?i)(^|/)SmartMart_Backup_[^/]*') {
            $sensitive += $path
        }
    }
    if ($sensitive.Count -gt 0) {
        Write-Host 'BLOCKED: Sensitive/private files are tracked or unignored:' -ForegroundColor Red
        $sensitive | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" }
        throw 'Do not run git add/push until these paths are excluded or safely untracked. No files were removed.'
    }
    Write-Host 'No obvious database, private-key, .env, media or backup paths in tracked/unignored files.' -ForegroundColor Green

    Write-Host "`n=== Files requiring special human review before commit ===" -ForegroundColor Cyan
    $review = @($candidates | Where-Object { $_ -match '(?i)\.(csv|xlsx|xls|pdf|zip)$' } | Sort-Object -Unique)
    if ($review.Count) {
        $review | Select-Object -First 35 | ForEach-Object { Write-Host "  $_" }
        if ($review.Count -gt 35) { Write-Host "  ... and $($review.Count - 35) more." }
        Write-Warning 'Review data files for customer, supplier or private information. Do not blindly commit them.'
    } else { Write-Host 'No tracked or unignored CSV, Excel, PDF or ZIP paths.' }

    Write-Host "`n=== Git branch, remote and status ===" -ForegroundColor Cyan
    Run-Step 'Current branch' 'git' @('branch','--show-current')
    Run-Step 'Configured remotes' 'git' @('remote','-v')
    Run-Step 'Uncommitted changes (review these manually)' 'git' @('status','--short')

    if ($SkipTests) {
        Write-Host "`nCHECKS COMPLETE WITH TESTS SKIPPED. Do not publish yet." -ForegroundColor Yellow
    } else {
        Write-Host "`nRELEASE CHECKS PASSED. Review git status and files before committing." -ForegroundColor Green
    }
    Write-Host 'Nothing was staged, committed, pushed or deployed by this script.'
} catch {
    Write-Host "`nRELEASE CHECK STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
