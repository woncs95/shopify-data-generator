$ErrorActionPreference = "Stop"

$ConfigDir = Join-Path $PSScriptRoot "config"
$SettingsPath = Join-Path $ConfigDir "settings.yml"

if (Test-Path $SettingsPath) {
    return
}

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$Secret = [guid]::NewGuid().ToString("N")

@"
use_default_settings: true

general:
  instance_name: "Shopify Product Research"

search:
  safe_search: 1
  default_lang: "en"
  formats:
    - html
    - json

server:
  bind_address: "0.0.0.0"
  secret_key: "$Secret"
  limiter: false
  image_proxy: true
"@ | Set-Content -Encoding utf8 $SettingsPath
