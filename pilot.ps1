<#
.SYNOPSIS
    One script for the in-person AffectLearn pilot: set up, start, create accounts, check, run
    sittings, export, back up, stop.

.DESCRIPTION
    Wraps docker-compose.pilot.yml and the pilot scripts so the facilitator never types the long
    commands. Run from the repository root. Works in Windows PowerShell 5.1 and PowerShell 7.

      .\pilot.ps1 all                       # first time: setup + start + 4 dry-run accounts + checks
      .\pilot.ps1 setup                     # create .env.pilot with generated secrets
      .\pilot.ps1 start                     # build, start, wait until healthy, seed the course
      .\pilot.ps1 accounts -Count 30 -Seed 20261001 -Lock
      .\pilot.ps1 status                    # health, frozen configuration, containers
      .\pilot.ps1 lock                      # freeze the gate configuration (before participant 1)
      .\pilot.ps1 check                     # pre-session readiness test (fake camera, demo account)
      .\pilot.ps1 session-start -Code P007  # facilitator: participant sat down (after paper consent)
      .\pilot.ps1 session-end -Code P007 -Reason completed -Notes "none"
      .\pilot.ps1 withdraw -Code P007       # erase a participant who asked for deletion
      .\pilot.ps1 export                    # pseudonymised dataset -> .\pilot_export-<time>
      .\pilot.ps1 backup                    # database dump -> .\backup-<time>.sql (encrypt it!)
      .\pilot.ps1 stop                      # stop, keep data
      .\pilot.ps1 reset                     # stop and DELETE ALL DATA (after dry runs)

    If scripts are blocked:  powershell -ExecutionPolicy Bypass -File .\pilot.ps1 all
    See docs/pilot/PILOT_RUN_CHECKLIST.md for when to use each step.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "all", "setup", "start", "accounts", "status", "lock", "check",
                 "session-start", "session-end", "withdraw", "export", "backup", "stop", "reset")]
    [string]$Command = "help",

    # accounts
    [int]$Count = 4,
    [int]$Seed = 20261001,
    [int]$Start = 1,
    [switch]$Lock,

    # sittings
    [string]$Code,
    [ValidateSet("completed", "withdrawn", "technical", "other")]
    [string]$Reason = "completed",
    [string]$Notes = "",
    [string]$Device = "",
    [string]$ProtocolVersion = "pilot-1.0",

    # setup
    [string]$OpenAIKey = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$EnvFile = Join-Path $Root ".env.pilot"
$EnvExample = Join-Path $Root ".env.pilot.example"
$AccountsFile = Join-Path $Root "pilot_accounts.csv"
$Api = "http://localhost:8000"

# ── helpers ───────────────────────────────────────────────────────────────────

function Say([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "    OK  $Text" -ForegroundColor Green }
function Warn([string]$Text) { Write-Host "    !!  $Text" -ForegroundColor Yellow }
function Fail([string]$Text) { Write-Host "    XX  $Text" -ForegroundColor Red; exit 1 }

function New-Secret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    # docker compose misreads the first key of an env file written with a BOM.
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding $false))
}

function Read-EnvFile {
    $values = @{}
    if (-not (Test-Path $EnvFile)) { return $values }
    foreach ($line in [System.IO.File]::ReadAllLines($EnvFile)) {
        if ($line -match '^\s*([A-Z0-9_]+)=(.*)$') { $values[$Matches[1]] = $Matches[2].Trim() }
    }
    return $values
}

function Invoke-Compose {
    # All compose calls go through here so the file set and env file are always the pilot ones.
    & docker compose -f (Join-Path $Root "docker-compose.yml") -f (Join-Path $Root "docker-compose.pilot.yml") `
        --env-file $EnvFile @args
    if ($LASTEXITCODE -ne 0) { Fail "docker compose $($args -join ' ') failed (exit $LASTEXITCODE)" }
}

function Assert-Docker {
    # Local to this function: in Windows PowerShell 5.1 a native command's stderr, once redirected,
    # becomes a terminating error under "Stop" -- a stopped Docker daemon would crash the script
    # instead of producing the message below.
    $ErrorActionPreference = "Continue"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Fail ("Docker is not installed. Install Docker Desktop (e.g. 'winget install Docker.DockerDesktop'), " +
              "start it, then run this again.")
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { Fail "Docker is installed but not running. Start Docker Desktop and wait for 'Engine running'." }
    $version = (& docker compose version --short) 2>$null
    if (-not $version) { Fail "'docker compose' (v2) is not available. Update Docker Desktop." }
    $parts = $version.TrimStart("v").Split(".")
    if ([int]$parts[0] -lt 2 -or ([int]$parts[0] -eq 2 -and [int]$parts[1] -lt 24)) {
        Fail "Docker Compose $version is too old; 2.24 or newer is needed (for '!reset'). Update Docker Desktop."
    }
}

function Assert-EnvFile {
    if (-not (Test-Path $EnvFile)) { Fail ".env.pilot not found. Run: .\pilot.ps1 setup" }
    $values = Read-EnvFile
    foreach ($key in "JWT_SECRET", "CONFIG_SECRET_KEY", "SEED_ADMIN_PASSWORD",
                     "SEED_LEARNER_PASSWORD", "SEED_DESIGNER_PASSWORD") {
        if (-not $values[$key]) { Fail "$key is empty in .env.pilot. Run: .\pilot.ps1 setup" }
    }
    if (-not $values["OPENAI_API_KEY"]) {
        Warn "OPENAI_API_KEY is empty: help messages will use the pre-written fallback text, not gpt-4o."
    }
}

function Get-AdminToken {
    $values = Read-EnvFile
    $body = @{ emailAddress = "admin@affectlearn.io"; password = $values["SEED_ADMIN_PASSWORD"] } | ConvertTo-Json
    try {
        $login = Invoke-RestMethod -Method Post -Uri "$Api/api/v1/auth/login" -ContentType "application/json" -Body $body -ErrorAction Stop
    } catch {
        Fail "Admin login failed ($($_.Exception.Message)). Is the stack running (.\pilot.ps1 start)?"
    }
    return $login.accessToken
}

function Invoke-Admin([string]$Method, [string]$Path, $Body = $null) {
    $headers = @{ Authorization = "Bearer $(Get-AdminToken)" }
    $params = @{ Method = $Method; Uri = "$Api/api/v1$Path"; Headers = $headers }
    if ($null -ne $Body) {
        $params["ContentType"] = "application/json"
        $params["Body"] = ($Body | ConvertTo-Json -Depth 6)
    }
    try {
        return Invoke-RestMethod @params -ErrorAction Stop
    } catch {
        $detail = $_.ErrorDetails.Message
        Fail "$Method $Path failed: $($_.Exception.Message) $detail"
    }
}

function Wait-Healthy([int]$TimeoutSeconds = 420) {
    Say "Waiting for the API to report healthy (first start can take a few minutes)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "$Api/health/pipeline" -TimeoutSec 5 -ErrorAction Stop
            if ($health.status -eq "ok") { Ok "pipeline healthy"; return $health }
        } catch { }
        Start-Sleep -Seconds 5
    }
    Fail "The API did not become healthy in $TimeoutSeconds s. Look at: .\pilot.ps1 status  and  docker compose logs api"
}

function Require-Code {
    if (-not $Code) { Fail "Give the participant code, e.g. -Code P007" }
    return $Code.ToUpper()
}

# ── commands ──────────────────────────────────────────────────────────────────

function Do-Setup {
    Say "Setting up .env.pilot"
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $EnvExample $EnvFile
        Ok "created .env.pilot from the example"
    }
    # LF throughout, so "(?m)...$" anchors at every line end (a CRLF checkout would otherwise leave a carriage return).
    $text = [System.IO.File]::ReadAllText($EnvFile) -replace "`r`n", "`n"
    foreach ($key in "JWT_SECRET", "CONFIG_SECRET_KEY", "SEED_ADMIN_PASSWORD",
                     "SEED_LEARNER_PASSWORD", "SEED_DESIGNER_PASSWORD") {
        if ($text -match "(?m)^$key=[ \t]*$") {
            $text = $text -replace "(?m)^$key=[ \t]*$", "$key=$(New-Secret)"
            Ok "generated $key"
        }
    }
    if ($text -match "(?m)^OPENAI_API_KEY=[ \t]*$") {
        $key = $OpenAIKey
        if (-not $key -and [Environment]::UserInteractive) {
            $key = Read-Host "OpenAI API key for gpt-4o (Enter to skip; help will use fallback text)"
        }
        if ($key) { $text = $text -replace "(?m)^OPENAI_API_KEY=[ \t]*$", "OPENAI_API_KEY=$key"; Ok "OPENAI_API_KEY set" }
        else { Warn "OPENAI_API_KEY left empty" }
    }
    Write-Utf8NoBom $EnvFile $text
    $admin = (Read-EnvFile)["SEED_ADMIN_PASSWORD"]
    Ok "facilitator login: admin@affectlearn.io / $admin  (also in .env.pilot; keep it private)"
}

function Do-Start {
    Assert-Docker
    Assert-EnvFile
    Push-Location $Root
    try { $commit = (& git rev-parse --short HEAD) 2>$null } finally { Pop-Location }
    if (-not $commit) { $commit = "unknown" }
    $env:APP_COMMIT = $commit
    Say "Building and starting the pilot stack (commit $commit)"
    Invoke-Compose up -d --build
    $health = Wait-Healthy
    if ($health.models.facial.kind -ne "geometry") { Warn "facial model kind is '$($health.models.facial.kind)', expected 'geometry'" }
    Say "Seeding the course content (safe to repeat)"
    Invoke-Compose exec -T api python -m app.db.seed_courses
    Ok "stack running: app http://localhost:3000   api http://localhost:8000"
}

function Do-Accounts {
    Assert-Docker
    Assert-EnvFile
    Say "Creating $Count participant account(s) from P$('{0:D3}' -f $Start) (seed $Seed) plus the readiness account"
    $composeArgs = @("exec", "-T", "api", "python", "-m", "scripts.create_pilot_participants",
              "--count", "$Count", "--seed", "$Seed", "--start", "$Start",
              "--out", "/app/pilot_accounts.csv", "--phase-b", "--readiness")
    if ($Lock) { $composeArgs += "--lock" }
    Invoke-Compose @composeArgs
    $ErrorActionPreference = "Continue"   # the copy below fails, by design, when nothing was created
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("pilot_accounts_" + [guid]::NewGuid().ToString("N") + ".csv")
    & docker compose -f (Join-Path $Root "docker-compose.yml") -f (Join-Path $Root "docker-compose.pilot.yml") `
        --env-file $EnvFile cp "api:/app/pilot_accounts.csv" $tmp 2>$null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tmp)) { Warn "no new accounts were created (all codes already exist)"; return }
    Invoke-Compose exec -T api rm -f /app/pilot_accounts.csv
    # Append to the local file, so re-running for more codes never overwrites earlier passwords.
    $lines = [System.IO.File]::ReadAllLines($tmp)
    if (Test-Path $AccountsFile) { $lines = $lines | Select-Object -Skip 1 }
    [System.IO.File]::AppendAllText($AccountsFile, (($lines -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding $false))
    Remove-Item $tmp -Force
    Ok "credentials appended to pilot_accounts.csv (git-ignored). Keep it encrypted; delete it after the pilot."
    Import-Csv $AccountsFile | Format-Table code, email, arm -AutoSize
    if (-not $Lock) { Warn "group assignments are NOT locked (fine for dry runs; use -Lock for the real pilot)" }
}

function Do-Status {
    Assert-Docker
    Assert-EnvFile
    Say "Containers"
    Invoke-Compose ps
    Say "Pipeline"
    try { $h = Invoke-RestMethod -Uri "$Api/health/pipeline" -TimeoutSec 5 -ErrorAction Stop } catch { Fail "API not reachable. Run: .\pilot.ps1 start" }
    "    status={0} redis={1} postgres={2} worker={3}" -f $h.status, $h.redis, $h.postgres, $h.worker.running
    "    facial={0} ({1})  behavioural={2}" -f $h.models.facial.kind, $h.models.facial.path, $h.models.behavioral.path
    Say "Frozen configuration (must match docs/pilot/protocol.md section 2)"
    $cfg = Invoke-Admin Get "/admin/config"
    $v = $cfg.values
    "    locked={0} version={1}" -f $cfg.locked, $cfg.version
    "    withholdRate={0} minConfidence={1} geometry={2} behavioural={3}" -f $v.withholdRate, $v.minConfidence, $v.minConfidenceGeometry, $v.minConfidenceBehavioral
    "    minConsecutive={0} cooldownCycles={1} maxPerSession={2} states={3} fusionDrives={4}" -f $v.minConsecutive, $v.cooldownCycles, $v.maxPerSession, ($v.adaptStates -join ","), $v.fusionDrivesDecision
    if ($v.withholdRate -ne 0) { Warn "withholdRate is not 0 (the between-group design needs 0)" }
    if (-not $cfg.locked) { Warn "configuration is not locked. Before participant 1: .\pilot.ps1 lock" }
    $sessions = @(Invoke-Admin Get "/admin/pilot/sessions")
    Say "Sittings: $($sessions.Count) recorded, $(@($sessions | Where-Object { -not $_.endedAt }).Count) open"
}

function Do-Lock {
    Say "Locking the gate configuration"
    $cfg = Invoke-Admin Post "/admin/config/lock" @{ locked = $true }
    Ok "locked=$($cfg.locked) version=$($cfg.version)"
}

function Do-Check {
    Say "Pre-session readiness check (automated system test; fake camera; demo-flagged account)"
    if (-not (Test-Path $AccountsFile)) { Fail "pilot_accounts.csv not found. Run: .\pilot.ps1 accounts" }
    $ready = Import-Csv $AccountsFile | Where-Object { $_.code -eq "READY" } | Select-Object -First 1
    if (-not $ready) { Fail "No READY account in pilot_accounts.csv. Run: .\pilot.ps1 accounts" }
    $frontend = Join-Path $Root "frontend"
    Push-Location $frontend
    try {
        if (-not (Test-Path (Join-Path $frontend "node_modules\.bin\playwright*"))) {
            Say "Installing frontend test dependencies (first time only)"
            & npm ci; if ($LASTEXITCODE -ne 0) { Fail "npm ci failed" }
        }
        & npx playwright install chromium; if ($LASTEXITCODE -ne 0) { Fail "playwright browser install failed" }
        $env:PILOT_READINESS = "1"
        $env:PILOT_READINESS_EMAIL = $ready.email
        $env:PILOT_READINESS_PASSWORD = $ready.password
        $env:PILOT_ADMIN_PASSWORD = (Read-EnvFile)["SEED_ADMIN_PASSWORD"]
        & npx playwright test e2e/pilot-readiness.spec.ts --reporter=line
        $code = $LASTEXITCODE
    } finally {
        Remove-Item Env:PILOT_READINESS_PASSWORD, Env:PILOT_ADMIN_PASSWORD -ErrorAction SilentlyContinue
        Pop-Location
    }
    if ($code -ne 0) { Fail "readiness check FAILED. Do not start a participant session until it passes." }
    Ok "readiness check passed"
}

function Do-SessionStart {
    $c = Require-Code
    $body = @{ participantCode = $c; protocolVersion = $ProtocolVersion }
    if ($Device) { $body["device"] = @{ notes = $Device } }
    $s = Invoke-Admin Post "/admin/pilot/sessions" $body
    Ok "sitting started for $c  arm=$($s.group)  phase=$($s.phase)  id=$($s.id)"
    if ($s.phase -ne "phase_b") { Warn "study phase is '$($s.phase)', not phase_b. Did you run accounts with -Count and --phase-b?" }
}

function Do-SessionEnd {
    $c = Require-Code
    $open = @(Invoke-Admin Get "/admin/pilot/sessions" | Where-Object { $_.participantCode -eq $c -and -not $_.endedAt })
    if ($open.Count -eq 0) { Fail "No open sitting for $c" }
    $s = Invoke-Admin Post "/admin/pilot/sessions/$($open[-1].id)/end" @{ endReason = $Reason; deviationNotes = $Notes }
    Ok "sitting ended for $c  reason=$($s.endReason)  at=$($s.endedAt)"
}

function Do-Withdraw {
    $c = Require-Code
    $email = "$($c.ToLower())@pilot.invalid"
    $page = Invoke-Admin Get "/admin/users?search=$([uri]::EscapeDataString($email))"
    $user = @($page.items | Where-Object { $_.emailAddress -eq $email }) | Select-Object -First 1
    if (-not $user) { Fail "No account for $c" }
    $answer = Read-Host "Permanently erase ALL data for $c ($email)? Type ERASE to confirm"
    if ($answer -ne "ERASE") { Warn "cancelled"; return }
    $receipt = Invoke-Admin Post "/admin/users/$($user.id)/withdraw"
    Ok "erased $c"
    $receipt | Format-List
    Warn "Also end the sitting:  .\pilot.ps1 session-end -Code $c -Reason withdrawn -Notes ""erasure requested"""
    Warn "Backups taken before now still hold this participant: record the withdrawal in the deviation log."
}

function Do-Export {
    Assert-Docker
    Assert-EnvFile
    $stamp = Get-Date -Format "yyyyMMdd-HHmm"
    $target = Join-Path $Root "pilot_export-$stamp"
    Say "Exporting the pseudonymised dataset"
    Invoke-Compose exec -T api python -m scripts.export_pilot --out /app/pilot_export
    Invoke-Compose cp "api:/app/pilot_export" $target
    Invoke-Compose exec -T api rm -rf /app/pilot_export
    Ok "exported to $target (git-ignored). Encrypt it before copying it anywhere."
}

function Do-Backup {
    Assert-Docker
    Assert-EnvFile
    $stamp = Get-Date -Format "yyyyMMdd-HHmm"
    $target = Join-Path $Root "backup-$stamp.sql"
    Say "Dumping the database"
    # Dumped inside the container and copied out: redirecting native output in Windows PowerShell
    # would re-encode the dump as UTF-16.
    Invoke-Compose exec -T db sh -c "pg_dump -U postgres affectlearn > /tmp/pilot-backup.sql"
    Invoke-Compose cp "db:/tmp/pilot-backup.sql" $target
    Invoke-Compose exec -T db rm -f /tmp/pilot-backup.sql
    Ok "backup written to $target"
    Warn "This file holds all research data in plain text: encrypt it (e.g. 7-Zip AES-256), store it off the laptop, delete the plain copy."
}

function Do-Stop {
    Assert-Docker
    Say "Stopping the stack (data is kept)"
    Invoke-Compose down
    Ok "stopped. Start again with: .\pilot.ps1 start"
}

function Do-Reset {
    Assert-Docker
    $answer = Read-Host "This DELETES ALL pilot data in the database. Type DELETE to confirm"
    if ($answer -ne "DELETE") { Warn "cancelled"; return }
    Invoke-Compose down -v
    Ok "stack removed and data volume deleted"
    if (Test-Path $AccountsFile) { Warn "pilot_accounts.csv still lists the old accounts; delete it before creating new ones." }
}

function Do-All {
    Do-Setup
    Do-Start
    Do-Accounts
    Do-Status
    Do-Check
    Say "Ready for a dry run. Open a Chrome Guest window at http://localhost:3000 and sign in as p001@pilot.invalid (password in pilot_accounts.csv)."
}

switch ($Command) {
    "help"          { Get-Help $PSCommandPath -Detailed }
    "all"           { Do-All }
    "setup"         { Do-Setup }
    "start"         { Do-Start }
    "accounts"      { Do-Accounts }
    "status"        { Do-Status }
    "lock"          { Do-Lock }
    "check"         { Do-Check }
    "session-start" { Do-SessionStart }
    "session-end"   { Do-SessionEnd }
    "withdraw"      { Do-Withdraw }
    "export"        { Do-Export }
    "backup"        { Do-Backup }
    "stop"          { Do-Stop }
    "reset"         { Do-Reset }
}
