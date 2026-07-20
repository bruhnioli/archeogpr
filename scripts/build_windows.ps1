<#
.SYNOPSIS
    Build the ArchaeoGPR Windows one-folder executable (Sprint GUI-1).

.DESCRIPTION
    Finds the repository root from this script's own location (not the
    caller's current directory), uses the project's own .venv\Scripts\
    python.exe (never a system/Anaconda interpreter), verifies the Qt
    package versions match and that PySide6.QtCore actually imports before
    spending time on a PyInstaller build, refuses to proceed if a previous
    ArchaeoGPR.exe is still running (never force-closes it for you), cleans
    only this app's own build/dist output (never a general git-clean), runs
    PyInstaller against packaging/archaeogpr.spec, and finishes with a
    --smoke-test run of the frozen executable.

    Settings isolation (ADR-018 Addendum): the smoke test runs with
    ARCHAEOGPR_WINDOW_STATE_PATH pointed at a throwaway temp file, and this
    script proves the real %LOCALAPPDATA%\ArchaeoGPR\window_state.ini was
    never read, written, created, or cleared by recording its hash/size (or
    absence) before the smoke test and verifying it is byte-for-byte
    identical (or still absent) after.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#>

$ErrorActionPreference = "Stop"

# 1. Repository root from this script's own location -------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot
Write-Output "Repository root: $RepoRoot"
Set-Location $RepoRoot

# 2. Project venv's own python.exe -------------------------------------------
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Project venv not found at $Python. Create it first: py -3.12 -m venv .venv (or -3.13); then pip install -e `".[dev,gui-test,packaging]`""
    exit 1
}
Write-Output "Using interpreter: $Python"

# 3. Refuse a broken/wrong interpreter (Anaconda/Miniconda/Microsoft Store) --
$InterpreterInfo = & $Python -c "import sys; print(sys.executable)"
if ($InterpreterInfo -match "(?i)anaconda|miniconda|WindowsApps") {
    Write-Error "Refusing to build with a conda/Microsoft Store interpreter ($InterpreterInfo). Use a python.org CPython venv -- see obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime.md."
    exit 1
}

# 4. Qt package versions must match exactly ----------------------------------
# Written to a temp .py file rather than passed inline via `-c` -- PowerShell
# 5.1's native-argv marshalling mangles embedded double quotes (confirmed
# while writing this script: an f-string's quotes were silently stripped),
# so a script file is the reliable way to hand Python a multi-line check.
Write-Output "Checking Qt package versions..."
$QtVersionCheckScript = Join-Path $env:TEMP "archaeogpr_qt_version_check.py"
@'
import importlib.metadata as m

names = ["PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6"]
versions = {}
for name in names:
    try:
        versions[name] = m.version(name)
    except m.PackageNotFoundError:
        print("MISSING:" + name)
        raise SystemExit(1)
for name, version in versions.items():
    print(name + "==" + version)
if len(set(versions.values())) != 1:
    print("MISMATCH")
    raise SystemExit(1)
print("OK")
'@ | Set-Content -Path $QtVersionCheckScript -Encoding utf8

$VersionCheck = & $Python $QtVersionCheckScript
$VersionCheckExit = $LASTEXITCODE
Remove-Item -Force $QtVersionCheckScript -ErrorAction SilentlyContinue
if ($VersionCheckExit -ne 0) {
    Write-Error "Qt package version check failed:`n$VersionCheck"
    exit 1
}
Write-Output $VersionCheck

# 5. QtCore import smoke test (the exact failure mode this project hit with
#    an Anaconda-based venv -- must pass before spending time on a build) ---
Write-Output "Running QtCore/QtWidgets/pyqtgraph import smoke test..."
$QtImportSmokeScript = Join-Path $env:TEMP "archaeogpr_qt_import_smoke.py"
@'
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QApplication
import pyqtgraph

print("Qt import smoke test OK, Qt", qVersion(), "pyqtgraph", pyqtgraph.__version__)
'@ | Set-Content -Path $QtImportSmokeScript -Encoding utf8

& $Python $QtImportSmokeScript
$ImportSmokeExit = $LASTEXITCODE
Remove-Item -Force $QtImportSmokeScript -ErrorAction SilentlyContinue
if ($ImportSmokeExit -ne 0) {
    Write-Error "PySide6/pyqtgraph failed to import in $Python -- fix this before building (see ADR-012). Not attempting a PyInstaller build against a broken Qt install."
    exit 1
}

# 6. Preflight: refuse to proceed if a previous build is still running -------
# A running ArchaeoGPR.exe locks its own _internal\*.pyd/.dll files, which
# turns the cleanup below into a wall of unrecoverable per-file Remove-Item
# errors. Fail fast with one clear message instead -- this script never
# force-closes a running GUI process on the user's behalf; silently killing
# it would be a surprising, hard-to-reverse action outside this script's
# remit, regardless of whether this particular app has unsaved state to lose.
$RunningInstance = Get-Process -Name "ArchaeoGPR" -ErrorAction SilentlyContinue
if ($RunningInstance) {
    $Pids = ($RunningInstance | Select-Object -ExpandProperty Id) -join ", "
    Write-Error "ArchaeoGPR.exe is currently running (PID $Pids). Close it before rebuilding -- this script never force-closes a running instance for you."
    exit 1
}

# 7. Clean only this app's own build/dist output, never a general clean -----
$BuildDir = Join-Path $RepoRoot "build\ArchaeoGPR"
$DistDir = Join-Path $RepoRoot "dist\ArchaeoGPR"
foreach ($path in @($BuildDir, $DistDir)) {
    if (Test-Path $path) {
        Write-Output "Removing previous build output: $path"
        Remove-Item -Recurse -Force $path
    }
}

# 8. Run PyInstaller ----------------------------------------------------------
Write-Output "Running PyInstaller..."
& $Python -m PyInstaller (Join-Path $RepoRoot "packaging\archaeogpr.spec") --distpath (Join-Path $RepoRoot "dist") --workpath (Join-Path $RepoRoot "build") --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed (exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}

# 9. Output executable path ---------------------------------------------------
$ExePath = Join-Path $RepoRoot "dist\ArchaeoGPR\ArchaeoGPR.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Build reported success but $ExePath does not exist."
    exit 1
}
Write-Output "Built executable: $ExePath"

# 10. Settings isolation for the smoke test (ADR-018 Addendum) ----------------
# The real window-state file this build verification must never touch --
# recorded (or its absence recorded) now, and re-checked byte-for-byte after
# the smoke test below, so this script itself proves it never read, wrote,
# created, or cleared the developer's actual saved layout.
$RealWindowStatePath = Join-Path $env:LOCALAPPDATA "ArchaeoGPR\window_state.ini"
$RealStateExistedBefore = Test-Path $RealWindowStatePath
if ($RealStateExistedBefore) {
    $RealStateBefore = Get-FileHash -Path $RealWindowStatePath -Algorithm SHA256
    $RealStateBeforeInfo = Get-Item $RealWindowStatePath
    Write-Output "Real window_state.ini present before smoke test: $($RealStateBeforeInfo.Length) bytes, sha256 $($RealStateBefore.Hash)"
} else {
    Write-Output "Real window_state.ini does not exist before smoke test (expected on a fresh machine)."
}

# A unique per-run temp path -- never the real file -- so the smoke-test
# subprocess (which additionally passes persist_window_state=False, see
# app.py) has nothing real to touch even if that guard were ever removed.
$SmokeWindowStatePath = Join-Path $env:TEMP "archaeogpr_build_smoke_window_state_$PID.ini"
$env:ARCHAEOGPR_WINDOW_STATE_PATH = $SmokeWindowStatePath

# 11. Smoke test the frozen executable ----------------------------------------
Write-Output "Running frozen executable smoke test..."
& $ExePath --smoke-test
$SmokeExitCode = $LASTEXITCODE

Remove-Item -Path $SmokeWindowStatePath -Force -ErrorAction SilentlyContinue
Remove-Item Env:ARCHAEOGPR_WINDOW_STATE_PATH -ErrorAction SilentlyContinue

if ($SmokeExitCode -ne 0) {
    Write-Error "Frozen executable smoke test failed (exit code $SmokeExitCode)."
    exit $SmokeExitCode
}
Write-Output "Frozen executable smoke test passed."

# 12. Verify the real window-state file was never touched ---------------------
$RealStateExistsAfter = Test-Path $RealWindowStatePath
if ($RealStateExistedBefore -ne $RealStateExistsAfter) {
    Write-Error "Settings-isolation violation: real window_state.ini existed=$RealStateExistedBefore before the smoke test but existed=$RealStateExistsAfter after."
    exit 1
}
if ($RealStateExistedBefore) {
    $RealStateAfter = Get-FileHash -Path $RealWindowStatePath -Algorithm SHA256
    if ($RealStateAfter.Hash -ne $RealStateBefore.Hash) {
        Write-Error "Settings-isolation violation: real window_state.ini's SHA-256 changed during the smoke test ($($RealStateBefore.Hash) -> $($RealStateAfter.Hash))."
        exit 1
    }
    Write-Output "Real window_state.ini unchanged by the smoke test (sha256 $($RealStateAfter.Hash))."
} else {
    Write-Output "Real window_state.ini still does not exist after the smoke test (as expected)."
}
Write-Output "Build complete: $ExePath"
