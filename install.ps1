param(
    [string]$Version = $(if ($env:VISUAL_EVIDENCE_GATEWAY_VERSION) { $env:VISUAL_EVIDENCE_GATEWAY_VERSION } else { "latest" }),
    [switch]$SkipProbe
)

$ErrorActionPreference = "Stop"
$Repo = if ($env:VISUAL_EVIDENCE_GATEWAY_REPO) { $env:VISUAL_EVIDENCE_GATEWAY_REPO } else { "scy7796/visual-evidence-gateway" }
$BinDir = if ($env:VISUAL_EVIDENCE_GATEWAY_BIN_DIR) {
    $env:VISUAL_EVIDENCE_GATEWAY_BIN_DIR
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "VisualEvidenceGateway\bin"
} else {
    Join-Path $HOME ".visual-evidence-gateway\bin"
}
$InstallPath = Join-Path $BinDir "visual-evidence-gateway.exe"

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
    "x64" { $Asset = "visual-evidence-gateway-windows-x86_64.exe" }
    "arm64" { throw "Windows ARM64 prebuilt binary is not published yet; run this installer on an x64 machine or build from source." }
    default { throw "Unsupported CPU architecture: $Arch" }
}

if ($env:VISUAL_EVIDENCE_GATEWAY_RELEASE_BASE) {
    $Base = $env:VISUAL_EVIDENCE_GATEWAY_RELEASE_BASE.TrimEnd('/')
} elseif ($Version -eq "latest") {
    $Base = "https://github.com/$Repo/releases/latest/download"
} else {
    $Tag = if ($Version.StartsWith("v")) { $Version } else { "v$Version" }
    $Base = "https://github.com/$Repo/releases/download/$Tag"
}

$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("visual-evidence-gateway-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
try {
    $Download = Join-Path $TempDir $Asset
    Write-Host "Downloading $Asset..."
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/$Asset" -OutFile $Download

    $ChecksumFile = Join-Path $TempDir "SHA256SUMS.txt"
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/visual-evidence-gateway-SHA256SUMS.txt" -OutFile $ChecksumFile
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
        Write-Host "Added $BinDir to your user PATH. Open a new terminal to use 'visual-evidence-gateway'."
    }
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TempDir
}
