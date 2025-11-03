# PowerShell script to setup and run GitHub Actions locally
# This will download and configure a self-hosted runner for GitHub Actions

param(
    [Parameter(Mandatory=$false)]
    [string]$Token = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$RemoveRunner = $false
)

Write-Host "=== GitHub Actions Local Runner Setup ===" -ForegroundColor Green
Write-Host ""

# Check prerequisites
$missing = @()

# Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker not found" -ForegroundColor Red
    $missing += "Docker Desktop"
} else {
    Write-Host "✅ Docker found: $(docker --version)" -ForegroundColor Green
}

# Check Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Git not found" -ForegroundColor Red
    $missing += "Git"
} else {
    Write-Host "✅ Git found: $(git --version)" -ForegroundColor Green
}

# Check PowerShell version (need 5.1+)
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Host "❌ PowerShell version too old (need 5.1+)" -ForegroundColor Red
    $missing += "PowerShell 5.1+"
} else {
    Write-Host "✅ PowerShell version: $($PSVersionTable.PSVersion)" -ForegroundColor Green
}

Write-Host ""

# If missing requirements, show installation instructions
if ($missing.Count -gt 0) {
    Write-Host "Missing required software:" -ForegroundColor Red
    foreach ($item in $missing) {
        Write-Host "  - $item" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Installation instructions:" -ForegroundColor Cyan
    Write-Host ""
    
    if ($missing -contains "Docker Desktop") {
        Write-Host "  Docker Desktop:" -ForegroundColor White
        Write-Host "    https://www.docker.com/products/docker-desktop" -ForegroundColor Gray
        Write-Host "    - Download and install Docker Desktop for Windows" -ForegroundColor Gray
        Write-Host "    - Make sure WSL 2 is enabled (Docker Desktop will prompt you)" -ForegroundColor Gray
        Write-Host ""
    }
    
    if ($missing -contains "Git") {
        Write-Host "  Git:" -ForegroundColor White
        Write-Host "    https://git-scm.com/download/win" -ForegroundColor Gray
        Write-Host "    - Download and install Git for Windows" -ForegroundColor Gray
        Write-Host ""
    }
    
    if ($missing -contains "PowerShell 5.1+") {
        Write-Host "  PowerShell:" -ForegroundColor White
        Write-Host "    PowerShell 5.1 comes with Windows 10/11" -ForegroundColor Gray
        Write-Host "    Or install PowerShell 7+ from: https://aka.ms/powershell-release" -ForegroundColor Gray
        Write-Host ""
    }
    
    exit 1
}

Write-Host "All prerequisites are installed! ✓" -ForegroundColor Green
Write-Host ""

# Remove existing runner
if (Test-Path "_runner") {
    if ($RemoveRunner) {
        Write-Host "Removing existing runner..." -ForegroundColor Yellow
        Set-Location _runner
        .\config.cmd remove --token $Token
        Set-Location ..
        Remove-Item -Recurse -Force _runner
        Write-Host "Runner removed successfully" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "Warning: Runner directory already exists" -ForegroundColor Yellow
        Write-Host "Use -RemoveRunner to remove it first" -ForegroundColor Yellow
        exit 1
    }
}

# Prompt for token if not provided
if ([string]::IsNullOrEmpty($Token)) {
    Write-Host "You need a GitHub Personal Access Token with 'actions' permission" -ForegroundColor Yellow
    Write-Host "Get one from: https://github.com/settings/tokens/new" -ForegroundColor Cyan
    Write-Host "Select 'actions' scope and click 'Generate token'" -ForegroundColor Cyan
    Write-Host ""
    $Token = Read-Host "Enter your GitHub Personal Access Token"
}

if ([string]::IsNullOrEmpty($Token)) {
    Write-Host "Error: Token is required" -ForegroundColor Red
    exit 1
}

# Create runner directory
Write-Host "Creating runner directory..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path _runner -Force | Out-Null
Set-Location _runner

# Download runner
Write-Host "Downloading GitHub Actions runner..." -ForegroundColor Cyan
$zipFile = "actions-runner.zip"
# Get latest version
$latestRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/actions/runner/releases/latest"
$downloadUrl = ($latestRelease.assets | Where-Object { $_.name -like "actions-runner-win-x64-*.zip" }).browser_download_url
if ($null -eq $downloadUrl) {
    Write-Host "Error: Could not find runner download URL" -ForegroundColor Red
    exit 1
}
Write-Host "Downloading from: $downloadUrl" -ForegroundColor Gray
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile

Write-Host "Extracting runner..." -ForegroundColor Cyan
Expand-Archive -Path $zipFile -DestinationPath . -Force
Remove-Item $zipFile

Write-Host "Configuring runner..." -ForegroundColor Cyan
.\config.cmd --url https://github.com/quinteroac/comfyui-base-image --token $Token

Write-Host ""
Write-Host "Runner configured successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To start the runner, run:" -ForegroundColor Cyan
Write-Host "  cd _runner" -ForegroundColor White
Write-Host "  .\run.cmd" -ForegroundColor White
Write-Host ""
Write-Host "The runner will now execute GitHub Actions workflows on this machine" -ForegroundColor Yellow
Write-Host "This means it will use your local Docker and disk space to build images" -ForegroundColor Yellow

Set-Location ..

