# Interactive onboarding for QA-Job-Script (Windows PowerShell).
# Idempotent: safe to re-run; skips files that already exist.
param(
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message"
}

function Copy-IfMissing([string]$Source, [string]$Dest) {
    if (Test-Path -LiteralPath $Dest) {
        Write-Host "  keep  $Dest (already exists)"
    }
    else {
        Copy-Item -LiteralPath $Source -Destination $Dest
        Write-Host "  copy  $Source -> $Dest"
    }
}

function Write-ProfileChecklist {
    Write-Host ""
    Write-Host "  Profile checklist — edit config\profile.yaml before your first scrape."
    Write-Host "  Full field guide: docs\your-profile.md"
    Write-Host ""
    Write-Host "  Edit now:"
    Write-Host "    • owner              — label in logs"
    Write-Host "    • remote_preference  — fully_remote | hybrid_home_metro | any_us_remote"
    Write-Host "    • home_metro         — name (display), zip_anchor, place_names (matching)"
    Write-Host "    • silent_office_hubs — review defaults for misleading location columns"
    Write-Host "    • comp               — min_ceiling_usd, min_floor_usd, gate2_floor_usd"
    Write-Host "    • prescreen.stack_keywords — tools/skills for stack_hits"
    Write-Host "    • tracks.enable      — start with [A] if unsure"
    Write-Host ""
    Write-Host "  Optional — set later:"
    Write-Host "    • referrals.status_file      — warm/strong referral map"
    Write-Host "    • verified_remote_employers  — after you confirm remote employers"
    Write-Host "    • review_companies           — extra manual review tier"
    Write-Host "    • paths.application_index    — already-applied HTML export"
}

function Open-Doc {
    param([string]$DocPath)
    if (-not (Test-Path -LiteralPath $DocPath)) {
        Write-Warning "Missing $DocPath"
        return
    }
    try {
        Start-Process -FilePath $DocPath
    }
    catch {
        Write-Host "  Read: $DocPath"
    }
}

function Open-ProfileForEdit {
    $profile = Join-Path $RepoRoot "config\profile.yaml"
    $profileGuide = Join-Path $RepoRoot "docs\your-profile.md"
    if (-not (Test-Path -LiteralPath $profile)) {
        Write-Warning "Expected config\profile.yaml after template copy."
        return
    }
    Write-ProfileChecklist
    if ($NonInteractive) {
        Write-Host "  Non-interactive: edit config\profile.yaml and read docs\your-profile.md before your first scrape."
        return
    }
    $docAns = Read-Host "Open docs\your-profile.md now? [Y/n]"
    if ($docAns -eq "" -or $docAns -match "^[Yy]") {
        Open-Doc $profileGuide
    }
    $ans = Read-Host "Open config\profile.yaml in notepad now? [Y/n]"
    if ($ans -ne "" -and $ans -notmatch "^[Yy]") {
        Write-Host "  Remember to edit config\profile.yaml before running the scraper."
        return
    }
    try {
        notepad $profile
    }
    catch {
        Write-Host "  Open manually: $profile"
    }
}

Write-Step "QA-Job-Script onboarding"
Write-Host "Repo: $RepoRoot"

Write-Step "1/5 — Python check"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Warning "python not found. Install Python 3.10+ and re-run."
    exit 1
}
$pyVer = & python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
Write-Host "  python version: $pyVer"
& python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Python 3.10+ recommended (found $pyVer)."
}

Write-Step "2/5 — Virtual environment (optional)"
$venvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path -LiteralPath $venvActivate) {
    Write-Host "  .venv already exists"
}
elseif (-not $NonInteractive) {
    $ans = Read-Host "Create .venv here? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        & python -m venv .venv
        Write-Host "  created .venv"
    }
    else {
        Write-Host "  skipped venv"
    }
}
else {
    Write-Host "  non-interactive: skipping venv (run: python -m venv .venv)"
}

$pip = @("python", "-m", "pip")
if (Test-Path -LiteralPath $venvActivate) {
    . $venvActivate
    $pip = @("pip")
    Write-Host "  activated .venv"
}

Write-Step "3/5 — Install dependencies"
& @pip install -r requirements.txt

Write-Step "4/5 — Copy config templates (only if missing)"
New-Item -ItemType Directory -Force -Path applications, jobspy\results | Out-Null
Copy-IfMissing "config\profile.example.yaml" "config\profile.yaml"
Copy-IfMissing "config\ils_matrix.example.yaml" "config\ils_matrix.yaml"
Copy-IfMissing "config\skip_companies.txt.example" "applications\skip_companies.txt"
Write-Host "  ILS (Interview Likelihood Score) is optional until you enable triage post-gates."
Write-Host "  Matrix rubric and profile floors: docs/ils-matrix.md"

Write-Step "5/5 — Customize profile (required)"
Open-ProfileForEdit

Write-Host ""
Write-Host "  Profile field guide: docs\your-profile.md"
Write-Host ""
Write-Host "  Optional PowerShell aliases:"
Write-Host "    .\scripts\install_alias.ps1 -AliasName qa-job"
Write-Host ""
Write-Host "  Optional application index: see docs\installation.md"
Write-Host ""
Write-Host "  Dry-run / verify install:"
Write-Host "    `$env:QA_JOB_PROFILE='config/profile.test.yaml'; python -m pytest -q"
Write-Host "    python scripts\triage_jobspy_csv.py --help"
Write-Host "    python jobspy\run_search_locally.py   # first scrape (network; may take minutes)"
Write-Host ""
Write-Host "Done."
