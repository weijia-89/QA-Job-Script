# Install PowerShell functions for the QA-Job-Script pipeline (Windows).
param(
    [string]$AliasName = "qa-job",
    [string]$ProfilePath = ""
)

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $ProfilePath) {
    $ProfilePath = $PROFILE
}

$Marker = "# QA-Job-Script functions"
$Block = @"

$Marker
function $AliasName {
    Set-Location "$RepoRoot"
    python jobspy/run_search_locally.py @args
}
function ${AliasName}-triage {
    Set-Location "$RepoRoot"
    python scripts/triage_jobspy_csv.py --latest --no-post-gates @args
}
function ${AliasName}-triage-ils {
    Set-Location "$RepoRoot"
    python scripts/triage_jobspy_csv.py --latest @args
}
"@

if (Test-Path $ProfilePath) {
    $existing = Get-Content -Raw $ProfilePath
    if ($existing -match [regex]::Escape($Marker)) {
        Write-Host "Functions already present in $ProfilePath"
    } else {
        Add-Content -Path $ProfilePath -Value $Block
        Write-Host "Appended functions to $ProfilePath"
    }
} else {
    New-Item -Path $ProfilePath -ItemType File -Force | Out-Null
    Set-Content -Path $ProfilePath -Value $Block
    Write-Host "Created $ProfilePath with QA-Job-Script functions"
}

Write-Host ""
Write-Host "Restart PowerShell or run: . $ProfilePath"
Write-Host "Then run: $AliasName"
