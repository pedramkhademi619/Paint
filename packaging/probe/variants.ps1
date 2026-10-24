# Runs the frozen probe in several variants and prints which one can import torch.
# Never fails the job: the point is the printed table.
$ErrorActionPreference = "Continue"
$dist = "dist\probe"
$internal = Join-Path $dist "_internal"
$exe = Join-Path $dist "probe.exe"
$sys32 = Join-Path $env:SystemRoot "System32"
$runtime = @("vcruntime140.dll","vcruntime140_1.dll","msvcp140.dll","msvcp140_1.dll","msvcp140_2.dll",
             "msvcp140_atomic_wait.dll","msvcp140_codecvt_ids.dll","concrt140.dll","vcomp140.dll")

function Show-Versions($label) {
    Write-Host "`n=== runtime DLL versions ($label)"
    foreach ($n in $runtime) {
        foreach ($dir in @($internal, (Join-Path $internal "torch\lib"), $sys32)) {
            $p = Join-Path $dir $n
            if (Test-Path $p) { Write-Host ("{0,-28} {1,-14} {2}" -f $n, (Get-Item $p).VersionInfo.FileVersion, $dir) }
        }
    }
}

function Run-Probe($label, $extraEnv) {
    Write-Host "`n########## VARIANT: $label"
    $old = @{}
    foreach ($k in $extraEnv.Keys) { $old[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $extraEnv[$k]) }
    $out = & $exe 2>&1 | Out-String
    $code = $LASTEXITCODE
    foreach ($k in $extraEnv.Keys) { [Environment]::SetEnvironmentVariable($k, $old[$k]) }
    $first = ($out -split "`n" | Select-Object -Last 6) -join "`n"
    Write-Host $first
    $script:results += ("{0,-58} exit={1}" -f $label, $code)
}

$script:results = @()
Show-Versions "as built"
Write-Host "`n=== DLLs next to torch\lib (first 40)"
Get-ChildItem (Join-Path $internal "torch\lib") -Filter *.dll | Select-Object -First 40 | ForEach-Object { Write-Host $_.Name }

Run-Probe "V0 baseline (bundle exactly as PyInstaller made it)" @{}

# V1: drop the bundled Visual C++ runtime copies so the system's current ones are used
$backup = Join-Path $env:RUNNER_TEMP "rt_backup"; New-Item -ItemType Directory -Force $backup | Out-Null
foreach ($n in $runtime) { $p = Join-Path $internal $n; if (Test-Path $p) { Copy-Item $p $backup; Remove-Item $p } }
Run-Probe "V1 bundled VC runtime copies REMOVED (system ones used)" @{}

# V2: replace the bundled copies with the current system ones
foreach ($n in $runtime) { $s = Join-Path $sys32 $n; if ((Test-Path $s) -and (Test-Path (Join-Path $backup $n))) { Copy-Item $s $internal -Force } }
Run-Probe "V2 bundled copies REPLACED by System32 versions" @{}

# V3: restore originals, tell Intel OpenMP duplicates not to abort
Get-ChildItem $backup | ForEach-Object { Copy-Item $_.FullName $internal -Force }
Run-Probe "V3 originals + KMP_DUPLICATE_LIB_OK=TRUE" @{ KMP_DUPLICATE_LIB_OK = "TRUE" }

# V4: originals, torch\lib first on PATH
Run-Probe "V4 originals + torch\lib on PATH" @{ PATH = ((Resolve-Path (Join-Path $internal "torch\lib")).Path + ";" + $env:PATH) }

Write-Host "`n=== imports of c10.dll (dumpbin, if available)"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $vs = & $vswhere -latest -products * -property installationPath
    $dumpbin = Get-ChildItem "$vs\VC\Tools\MSVC" -Recurse -Filter dumpbin.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like "*Hostx64\x64*" } | Select-Object -First 1
    if ($dumpbin) { & $dumpbin.FullName /dependents (Join-Path $internal "torch\lib\c10.dll") | Select-String "\.dll" }
}

Write-Host "`n################ SUMMARY"
$script:results | ForEach-Object { Write-Host $_ }
exit 0
