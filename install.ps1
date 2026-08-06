param(
    [string]$Version = $(if ($env:VISIONSIEVE_VERSION) { $env:VISIONSIEVE_VERSION } elseif ($env:VISUAL_EVIDENCE_GATEWAY_VERSION) { $env:VISUAL_EVIDENCE_GATEWAY_VERSION } else { "latest" }),
    [switch]$SkipProbe
)

$ErrorActionPreference = "Stop"
$Repo = if ($env:VISIONSIEVE_REPO) { $env:VISIONSIEVE_REPO } elseif ($env:VISUAL_EVIDENCE_GATEWAY_REPO) { $env:VISUAL_EVIDENCE_GATEWAY_REPO } else { "scy7796/visionsieve-mcp" }
$BinDir = if ($env:VISIONSIEVE_BIN_DIR) {
    $env:VISIONSIEVE_BIN_DIR
} elseif ($env:VISUAL_EVIDENCE_GATEWAY_BIN_DIR) {
    $env:VISUAL_EVIDENCE_GATEWAY_BIN_DIR
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "VisionSieve\bin"
} else {
    Join-Path $HOME ".visionsieve\bin"
}
$InstallPath = Join-Path $BinDir "visionsieve.exe"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw @"
Codex CLI is required but was not found.
Install the official CLI first, sign in with ChatGPT, then rerun this command:
  npm install -g @openai/codex
  codex
"@
}

$Arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
switch ($Arch) {
    "x64" { $Asset = "visionsieve-windows-x86_64.exe" }
    "arm64" { throw "Windows ARM64 prebuilt binary is not published yet; run this installer on an x64 machine or build from source." }
    default { throw "Unsupported CPU architecture: $Arch" }
}

if ($env:VISIONSIEVE_RELEASE_BASE) {
    $Base = $env:VISIONSIEVE_RELEASE_BASE.TrimEnd('/')
} elseif ($env:VISUAL_EVIDENCE_GATEWAY_RELEASE_BASE) {
    $Base = $env:VISUAL_EVIDENCE_GATEWAY_RELEASE_BASE.TrimEnd('/')
} elseif ($Version -eq "latest") {
    $Base = "https://github.com/$Repo/releases/latest/download"
} else {
    $Tag = if ($Version.StartsWith("v")) { $Version } else { "v$Version" }
    $Base = "https://github.com/$Repo/releases/download/$Tag"
}

$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("visionsieve-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
try {
    $Download = Join-Path $TempDir $Asset
    Write-Host "Downloading $Asset..."
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/$Asset" -OutFile $Download

    $ChecksumFile = Join-Path $TempDir "SHA256SUMS.txt"
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/visionsieve-SHA256SUMS.txt" -OutFile $ChecksumFile
    $Line = Get-Content $ChecksumFile | Where-Object { $_ -match "\s\*?$([regex]::Escape($Asset))$" } | Select-Object -First 1
    if (-not $Line) { throw "SHA-256 checksum file does not contain an entry for $Asset" }
    $Expected = ($Line -split "\s+")[0].ToLowerInvariant()
    if ($Expected -notmatch '^[0-9a-f]{64}$') { throw "SHA-256 checksum entry is malformed" }
    $Actual = (Get-FileHash -Algorithm SHA256 -Path $Download).Hash.ToLowerInvariant()
    if ($Expected -ne $Actual) { throw "SHA-256 verification failed." }

    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    Move-Item -Force -Path $Download -Destination $InstallPath
    Write-Host "Installed: $InstallPath"

    $SetupArgs = @("setup")
    if ($SkipProbe) { $SetupArgs += "--skip-probe" }
    & $InstallPath @SetupArgs
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $InstallPath
        if (-not (Get-ChildItem -LiteralPath $BinDir -Force -ErrorAction SilentlyContinue)) {
            Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $BinDir
        }
        Write-Host "Setup failed with exit code $LASTEXITCODE; the downloaded binary was rolled back."
        exit $LASTEXITCODE
    }

    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $Parts = @($UserPath -split ";" | Where-Object { $_ })
    if ($Parts -notcontains $BinDir) {
        $NewPath = (($Parts + $BinDir) -join ";")
        [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
        Write-Host "Added $BinDir to your user PATH. Open a new terminal to use 'visionsieve'."
    }
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TempDir
}
