# Creates backend\.env interactively. Called by setup.bat.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root '.env'

function Ask($label, $default = '') {
    $suffix = ''
    if ($default -ne '') { $suffix = " [$default]" }
    $answer = Read-Host "$label$suffix"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim()
}

if (Test-Path $target) {
    $keep = Ask 'backend\.env already exists. Keep it? (Y/n)' 'Y'
    if ($keep -match '^[Yy]') { Write-Host 'Keeping existing .env'; exit 0 }
}

Write-Host ''
Write-Host 'How do you want to run Wire?'
Write-Host '  1) Local test   - no Supabase needed (SQLite file on this PC)'
Write-Host '  2) Supabase     - your real database (same logins as before)'
$mode = Ask 'Choose 1 or 2' '2'

$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$pepper = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')

$lines = New-Object System.Collections.Generic.List[string]
if ($mode -eq '1') {
    $lines.Add('ENVIRONMENT=development')
    $lines.Add('DATABASE_URL=sqlite:///./wire-dev.db')
    $hosts = 'localhost,127.0.0.1,10.0.2.2,testserver'
} else {
    Write-Host ''
    Write-Host 'Paste the two Supabase database URLs you already use (one line each).'
    Write-Host 'They look like postgresql+psycopg://wire_main_backend:...@...:5432/postgres?sslmode=verify-full&sslrootcert=...'
    $main = Ask 'DATABASE_URL (wire_main_backend)'
    $chat = Ask 'CHAT_DATABASE_URL (wire_chat_backend)'
    if (-not $main -or -not $chat) { Write-Host 'Both URLs are required for Supabase mode.'; exit 1 }
    $lines.Add('ENVIRONMENT=production')
    $lines.Add("DATABASE_URL=`"$main`"")
    $lines.Add("CHAT_DATABASE_URL=`"$chat`"")
    $hosts = Ask 'ALLOWED_HOSTS (comma separated)' 'localhost,127.0.0.1'
}

Write-Host ''
Write-Host 'Email (SMTP) sends the verification codes. Leave blank to fill in later.'
$smtpHost = Ask 'SMTP_HOST'
$smtpPort = Ask 'SMTP_PORT' '587'
$smtpUser = ''
$smtpPass = ''
$smtpFrom = ''
if ($smtpHost) {
    $smtpUser = Ask 'SMTP_USER'
    $smtpPass = Ask 'SMTP_PASSWORD'
    $smtpFrom = Ask 'SMTP_FROM (sender address)'
}

$lines.Add("ALLOWED_HOSTS=$hosts")
$lines.Add('SESSION_DAYS=7')
$lines.Add('RATE_LIMITS_ENABLED=true')
$lines.Add("EMAIL_CODE_PEPPER=$pepper")
$lines.Add("SMTP_HOST=$smtpHost")
$lines.Add("SMTP_PORT=$smtpPort")
$lines.Add("SMTP_USER=$smtpUser")
$lines.Add("SMTP_PASSWORD=$smtpPass")
$lines.Add("SMTP_FROM=$smtpFrom")

[System.IO.File]::WriteAllText($target, ($lines -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding $false))
Write-Host ''
Write-Host "Saved $target"
if (-not $smtpHost) { Write-Host 'NOTE: SMTP is empty, so signup emails cannot be sent until you fill SMTP_* in backend\.env.' }
