# Обновить em-note на VPS по SSH с этого ПК (Windows / PowerShell).
# Ключ по умолчанию — Timeweb: %USERPROFILE%\.ssh\id_ed25519_timeweb
#
# Пример (подставьте IP или хост Timeweb):
#   .\deploy\remote-update-vps.ps1 -VpsHost 85.198.83.132
#   .\deploy\remote-update-vps.ps1 -VpsHost 85.198.83.132 -DeployMode ghcr
#   .\deploy\remote-update-vps.ps1 -VpsHost 85.198.83.132 -VpsUser root -InstallDir /opt/em-note
#
# Перед запуском: дождитесь успешного GitHub Actions «Publish Docker images», если используете GHCR.

param(
  [Parameter(Mandatory = $true, HelpMessage = "IP или hostname VPS (Timeweb)")]
  [string] $VpsHost,

  [string] $VpsUser = "root",

  [string] $SshKey = "$env:USERPROFILE\.ssh\id_ed25519_timeweb",

  [string] $InstallDir = "/opt/em-note",

  [ValidateSet("auto", "ghcr", "prod")]
  [string] $DeployMode = "auto"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SshKey)) {
  Write-Error "SSH-ключ не найден: $SshKey. Укажите -SshKey или положите ключ по этому пути."
}

$remotePrefix = "cd $($InstallDir) && git pull --ff-only && "
if ($DeployMode -ne "auto") {
  $remoteCmd = "${remotePrefix}EM_NOTE_DEPLOY_MODE=$DeployMode bash deploy/vps-update.sh"
} else {
  $remoteCmd = "${remotePrefix}bash deploy/vps-update.sh"
}

Write-Host "SSH: $VpsUser@$VpsHost (key: $SshKey)" -ForegroundColor Cyan
Write-Host "Remote: $remoteCmd" -ForegroundColor Gray

& ssh -i $SshKey -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new `
  "$VpsUser@$VpsHost" $remoteCmd

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
Write-Host "Done." -ForegroundColor Green
