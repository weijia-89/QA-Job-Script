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

function Invoke-ProfileConfigure {
    $profile = Join-Path $RepoRoot "config\profile.yaml"
    if (-not (Test-Path -LiteralPath $profile)) {
        Write-Warning "Expected config\profile.yaml after template copy."
        return
    }
    if ($NonInteractive) {
        Write-Host "  Non-interactive: run python scripts\configure_profile.py when ready."
        return
    }
    Write-Host "  Starting interactive profile setup (press Enter to keep each default)."
    & python (Join-Path $RepoRoot "scripts\configure_profile.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "configure_profile.py exited with code $LASTEXITCODE"
    }
}

$ProfileGuide = Join-Path $RepoRoot "docs\your-profile.md"
$ProfileGuideUrl = "https://github.com/weijia-89/QA-Job-Script/blob/main/docs/your-profile.md"

function Open-ProfileGuide {
    Write-Host "  Opening your profile guide in browser..."
    if (Test-Path -LiteralPath $ProfileGuide) {
        $url = "file://$ProfileGuide"
        Write-Host "  $url"
        try {
            Start-Process -FilePath $ProfileGuide
        }
        catch {
            Write-Host "  (Could not open browser — read the file above)"
        }
    }
    else {
        Write-Host "  $ProfileGuideUrl"
        try {
            Start-Process -FilePath $ProfileGuideUrl
        }
        catch {
            Write-Host "  (Could not open browser — visit URL above)"
        }
    }
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

function Open-ProfileOptional {
    if ($NonInteractive) {
        return
    }
    $profile = Join-Path $RepoRoot "config\profile.yaml"
    $profileGuide = Join-Path $RepoRoot "docs\your-profile.md"
    $docAns = Read-Host "Open docs\your-profile.md for reference? [y/N]"
    if ($docAns -match "^[Yy]") {
        Open-Doc $profileGuide
    }
    $ans = Read-Host "Open config\profile.yaml in Notepad for fine-tuning? [y/N]"
    if ($ans -notmatch "^[Yy]") {
        return
    }
    try {
        notepad $profile
    }
    catch {
        Write-Host "  Open manually: $profile"
    }
}

Write-Step "Welcome — QA-Job-Script setup"
Write-Host "This script prepares the job-search tool on your computer."
Write-Host "Repo folder: $RepoRoot"

Write-Step "1/5 — Check for Python"
Write-Host "  Python is the runtime that runs the scraper; we need version 3.10 or newer."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Warning "python not found. Install Python 3.10+ (see docs\installation.md) and re-run."
    exit 1
}
$pyVer = & python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
Write-Host "  Found python version: $pyVer"
& python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Python 3.10+ recommended (found $pyVer)."
}

Write-Step "2/5 — Optional isolated environment (.venv)"
Write-Host "  A virtual environment keeps this project's packages separate from other apps."
$venvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path -LiteralPath $venvActivate) {
    Write-Host "  .venv already exists — skipping create"
}
elseif (-not $NonInteractive) {
    $ans = Read-Host "Create .venv in this folder? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        & python -m venv .venv
        Write-Host "  Created .venv"
    }
    else {
        Write-Host "  Skipped — you can create one later with: python -m venv .venv"
    }
}
else {
    Write-Host "  Non-interactive: skipping venv (run: python -m venv .venv)"
}

$pip = @("python", "-m", "pip")
if (Test-Path -LiteralPath $venvActivate) {
    . $venvActivate
    $pip = @("pip")
    Write-Host "  Activated .venv for the rest of this script"
}

Write-Step "3/5 — Install required packages"
Write-Host "  Downloading libraries listed in requirements.txt (JobSpy, YAML, etc.)."
Write-Host "  Installing from public PyPI (pypi.org), not your employer's private index."
$depCheck = & python (Join-Path $RepoRoot "scripts\check_onboard_deps.py") --check-only
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Dependencies already installed — skipping pip install"
}
else {
    & python (Join-Path $RepoRoot "scripts\check_onboard_deps.py")
    Remove-Item Env:PIP_INDEX_URL -ErrorAction SilentlyContinue
    Remove-Item Env:PIP_EXTRA_INDEX_URL -ErrorAction SilentlyContinue
    & @pip install -r requirements.txt `
      --index-url https://pypi.org/simple `
      --trusted-host pypi.org
}

Write-Step "4/5 — Copy starter settings (only if missing)"
Write-Host "  These are your personal config files — never overwritten if they already exist."
New-Item -ItemType Directory -Force -Path applications, jobspy\results | Out-Null
Copy-IfMissing "config\profile.example.yaml" "config\profile.yaml"
Copy-IfMissing "config\ils_matrix.example.yaml" "config\ils_matrix.yaml"
Copy-IfMissing "config\skip_companies.txt.example" "applications\skip_companies.txt"
Write-Host "  These files stay on your machine; git will not upload them."

Write-Step "5/5 — Customize your profile"
Write-Host "  profile.yaml tells the tool where you live, what pay to require, and which skills to look for."
Open-ProfileGuide
Invoke-ProfileConfigure
Open-ProfileOptional

Write-Host ""
Write-Host "────────────────────────────────────────"
Write-Host "  Setup complete."
Write-Host ""
Write-Host "  Before your first job search:"
Write-Host "    1. Profile ready in config\profile.yaml (re-run: python scripts\configure_profile.py)"
Write-Host "    2. Run: python jobspy\run_search_locally.py"
Write-Host "    3. Then: python scripts\triage_jobspy_csv.py --latest --no-post-gates"
Write-Host ""
Write-Host "  Optional shortcuts: .\scripts\install_alias.ps1 -AliasName qa-job"
Write-Host "  More help: docs\installation.md"
Write-Host ""
Write-Host "  When you are ready to tune interview-likelihood scoring, read:"
Write-Host "    docs\ils-matrix.md"
Write-Host "  (You can ignore that file for your first few runs.)"
Write-Host "────────────────────────────────────────"
Write-Host ""
Write-Host "Done."
