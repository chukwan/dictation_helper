param (
    [switch]$Rebuild
)

$VenvDir = "venv"

# Function to check if a command exists
function Test-CommandExists {
    param ($Command)
    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

# Check for Python
if (-not (Test-CommandExists python)) {
    Write-Error "Python is not installed or not in the PATH."
    exit 1
}

# Rebuild logic: Remove existing venv if requested
if ($Rebuild) {
    if (Test-Path $VenvDir) {
        Write-Host "Rebuild requested. Removing existing virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }
}

# Create venv if it doesn't exist
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment in '$VenvDir'..." -ForegroundColor Cyan
    python -m venv $VenvDir
    
    if (-not (Test-Path $VenvDir)) {
        Write-Error "Failed to create virtual environment."
        exit 1
    }
    
    Write-Host "Installing requirements..." -ForegroundColor Cyan
    & ".\$VenvDir\Scripts\pip.exe" install -r requirements.txt
} else {
    # If Rebuild was not requested but venv exists, we can optionally check for updates
    # But for now, we'll assume it's good unless Rebuild is passed.
    Write-Host "Virtual environment found." -ForegroundColor Green
}

# Run the app
$StreamlitPath = ".\$VenvDir\Scripts\streamlit.exe"

if (Test-Path $StreamlitPath) {
    Write-Host "Starting Dictation Buddy..." -ForegroundColor Cyan
    & $StreamlitPath run app.py
} else {
    Write-Error "Streamlit not found in virtual environment. Please run with -Rebuild to fix."
    exit 1
}
