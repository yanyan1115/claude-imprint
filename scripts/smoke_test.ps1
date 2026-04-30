param(
    [string]$MemoryHttpUrl,
    [string]$DashboardUrl,
    [string]$StatusUrl
)

$ErrorActionPreference = "Continue"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$PassCount = 0
$WarnCount = 0
$FailCount = 0

function Pass($Message) {
    $script:PassCount += 1
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Warn($Message) {
    $script:WarnCount += 1
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Fail($Message) {
    $script:FailCount += 1
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Load-DotEnv {
    if (-not (Test-Path ".env")) {
        Warn ".env not found; using defaults and current environment"
        return
    }

    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Pass ".env loaded"
}

function Expand-ConfigPath([string]$PathValue) {
    if (-not $PathValue) {
        return $PathValue
    }
    if ($PathValue -eq "~") {
        return $HOME
    }
    if ($PathValue.StartsWith("~/") -or $PathValue.StartsWith("~\")) {
        return (Join-Path $HOME $PathValue.Substring(2))
    }
    return $PathValue
}

function Get-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return $python3.Source
    }
    return $null
}

function Test-HttpReachable([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return [int]$response.StatusCode
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and $resp.StatusCode) {
            return [int]$resp.StatusCode
        }
        throw
    }
}

function Test-SqliteSchema([string]$Python, [string]$DbPath) {
    $code = @'
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
conn = sqlite3.connect(str(db_path))
try:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    required = {"memories", "conversation_log", "summaries"}
    missing = sorted(required - tables)
    if missing:
        print("MISSING:" + ",".join(missing))
        sys.exit(2)
    counts = {}
    for table in ("memories", "conversation_log", "summaries"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(counts)
finally:
    conn.close()
'@
    return $code | & $Python - $DbPath
}

Write-Host "Claude Imprint smoke test"
Write-Host "Project: $RootDir"
Write-Host ""

Load-DotEnv

$Python = Get-PythonCommand
if (-not $Python) {
    Fail "Python not found"
} else {
    $Version = & $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    & $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -eq 0) {
        Pass "Python $Version"
    } else {
        Fail "Python $Version found, but Python 3.11+ is recommended"
    }
}

if (Test-Path "requirements.txt") {
    Pass "requirements.txt found"
} else {
    Fail "requirements.txt missing"
}

if (Test-Path "docker-compose.yml") {
    Pass "docker-compose.yml found"
} else {
    Warn "docker-compose.yml missing"
}

if (Test-Path ".env.example") {
    Pass ".env.example found"
} else {
    Fail ".env.example missing"
}

$Docker = Get-Command docker -ErrorAction SilentlyContinue
if ($Docker) {
    & docker compose --env-file .env.example config --quiet *> $null
    if ($LASTEXITCODE -eq 0) {
        Pass "docker compose config is valid"
    } else {
        Fail "docker compose config failed"
    }
} else {
    Warn "docker compose not available; skipped compose validation"
}

if ($Python) {
    foreach ($Module in @("fastapi", "psutil", "yaml")) {
        & $Python -c "import $Module" *> $null
        if ($LASTEXITCODE -eq 0) {
            Pass "Python module import ok: $Module"
        } else {
            Warn "Python module not importable yet: $Module"
        }
    }
}

$MemoryPort = if ($env:MEMORY_HTTP_PORT) { $env:MEMORY_HTTP_PORT } else { "8000" }
$DashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "3000" }
if (-not $MemoryHttpUrl) {
    $MemoryHttpUrl = "http://127.0.0.1:$MemoryPort/mcp"
}
if (-not $DashboardUrl) {
    $DashboardUrl = "http://127.0.0.1:$DashboardPort"
}
if (-not $StatusUrl) {
    $StatusUrl = "$($DashboardUrl.TrimEnd('/'))/api/status"
}

try {
    $Code = Test-HttpReachable $MemoryHttpUrl
    if ($Code -ge 200 -and $Code -lt 500) {
        Pass "Memory HTTP reachable: $MemoryHttpUrl (HTTP $Code)"
    } else {
        Warn "Memory HTTP responded with HTTP $Code`: $MemoryHttpUrl"
    }
} catch {
    Fail "Memory HTTP not reachable: $MemoryHttpUrl"
}

try {
    $Status = Invoke-RestMethod -Uri $StatusUrl -TimeoutSec 5
    Pass "Dashboard status JSON reachable: $StatusUrl"
    foreach ($Key in @("memory_http", "tunnel", "telegram")) {
        $Comp = $Status.components.$Key
        if ($Comp) {
            Write-Host "  - $Key`: running=$($Comp.running) pid=$($Comp.pid)"
        }
    }
    if ($Status.memory) {
        Write-Host "  - memories=$($Status.memory.count) today_logs=$($Status.memory.today_logs)"
    }
} catch {
    Fail "Dashboard status JSON not reachable: $StatusUrl"
}

$DataDirRaw = if ($env:IMPRINT_DATA_DIR) { $env:IMPRINT_DATA_DIR } else { Join-Path $HOME ".imprint" }
$DataDir = Expand-ConfigPath $DataDirRaw
$DbPath = if ($env:IMPRINT_DB) { Expand-ConfigPath $env:IMPRINT_DB } else { Join-Path $DataDir "memory.db" }

if (Test-Path $DataDir -PathType Container) {
    Pass "IMPRINT_DATA_DIR exists: $DataDir"
} else {
    Warn "IMPRINT_DATA_DIR does not exist yet: $DataDir"
}

if (Test-Path $DbPath -PathType Leaf) {
    if ($Python) {
        try {
            $Result = Test-SqliteSchema $Python $DbPath
            Pass "SQLite schema readable: $DbPath"
            Write-Host "  - table counts: $Result"
        } catch {
            Fail "SQLite schema check failed: $DbPath"
        }
    } else {
        Warn "SQLite schema skipped because Python is missing"
    }
} else {
    Warn "memory.db not found yet: $DbPath"
}

$RecentContext = Join-Path $DataDir "recent_context.md"
if (Test-Path $RecentContext -PathType Leaf) {
    Pass "recent_context.md found"
} else {
    Warn "recent_context.md not found yet; it appears after hooks/channel activity"
}

if ($env:TELEGRAM_BOT_TOKEN -and $env:TELEGRAM_CHAT_ID) {
    Pass "Telegram send env configured"
} else {
    Warn "Telegram send env incomplete; set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID when enabling Telegram notifications"
}

Write-Host ""
Write-Host "Summary: $PassCount passed, $WarnCount warnings, $FailCount failed"
if ($FailCount -gt 0) {
    exit 1
}
