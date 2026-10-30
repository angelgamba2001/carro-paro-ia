# Despliega SMARTDATA 360 - Carro de Paro en Azure Container Apps (HTTPS incluido).
#
# Requisitos: Azure CLI (winget install -e --id Microsoft.AzureCLI) y "az login".
# Uso, desde la raiz del repo en PowerShell:
#     .\despliegue\azure\desplegar_containerapps.ps1
# Se puede volver a ejecutar para publicar una version nueva (usa el ultimo commit).
# Requiere Docker Desktop encendido: las imagenes se construyen en este equipo y se
# suben al registro (las cuentas de prueba de Azure no permiten ACR Tasks / az acr build).
param(
    [string]$Grupo   = "rg-carro-paro",
    [string]$Region  = "brazilsouth",
    [string]$Entorno = "cae-carro-paro",
    [string]$App     = "carro-paro-web"
)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"          # evita errores de az con tildes en los logs
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Invoke-Az {
    & az @args
    if ($LASTEXITCODE -ne 0) { throw "Fallo el comando: az $($args -join ' ')" }
}
function Invoke-Nativo {
    $exe, $resto = $args
    & $exe @resto
    if ($LASTEXITCODE -ne 0) { throw "Fallo el comando: $($args -join ' ')" }
}
function Get-BytesAleatorios([int]$n) {
    $b = New-Object byte[] $n
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ,$b
}

$raiz = (git rev-parse --show-toplevel)
Set-Location $raiz
if (git status --porcelain) {
    Write-Warning "Hay cambios sin commit: la imagen se construye con el ultimo commit (HEAD), no con ellos."
}
$tag = (git rev-parse --short HEAD)

Write-Host "==> 1/7 Extension de Container Apps para Azure CLI" -ForegroundColor Cyan
Invoke-Az extension add --name containerapp --upgrade --only-show-errors

Write-Host "==> 2/7 Grupo de recursos $Grupo ($Region)" -ForegroundColor Cyan
# Si el grupo ya existe se reutiliza: su ubicacion es solo metadato y los recursos
# se crean igual en $Region.
$grupoExiste = az group exists --name $Grupo
if ($grupoExiste -ne "true") {
    Invoke-Az group create --name $Grupo --location $Region -o none
} else {
    Write-Host "    El grupo ya existe; se reutiliza (los recursos van en $Region)."
}

Write-Host "==> 3/7 Registro de contenedores (ACR Basic)" -ForegroundColor Cyan
$acr = az acr list -g $Grupo --query "[0].name" -o tsv
if (-not $acr) {
    $acr = "carroparo" + (Get-Random -Minimum 10000 -Maximum 99999)
    Invoke-Az acr create -g $Grupo -n $acr --sku Basic --admin-enabled true -l $Region -o none
}
$acrServidor = "$acr.azurecr.io"
Write-Host "    Registro: $acrServidor"

Write-Host "==> 4/7 Construccion local y subida de imagenes (la primera vez 20-40 min segun tu internet)" -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "No se encontro Docker. Instala y abre Docker Desktop, y vuelve a ejecutar el script."
}
$ErrorActionPreference = "Continue"     # docker info escribe avisos en stderr: que no detengan el script
& docker info *> $null
$dockerOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $dockerOk) { throw "Docker no responde. Abre Docker Desktop, espera a que diga 'Engine running' y reintenta." }
Invoke-Az acr login -n $acr
$fuente = Join-Path $env:TEMP "carro-paro-src-$tag"
$zip = "$fuente.zip"
if (Test-Path $fuente) { Remove-Item $fuente -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
git archive --format=zip -o $zip HEAD     # solo lo versionado: sin .env, venv ni data lake local
Expand-Archive $zip -DestinationPath $fuente -Force
$imgApp   = "$acrServidor/carro-paro-ia:$tag"
$imgNginx = "$acrServidor/carro-paro-nginx:$tag"
Invoke-Nativo docker build --platform linux/amd64 -t $imgApp $fuente
Invoke-Nativo docker build --platform linux/amd64 -t $imgNginx (Join-Path $fuente "despliegue\azure\nginx")
Invoke-Nativo docker push $imgApp
Invoke-Nativo docker push $imgNginx
# MySQL se copia al registro propio (sin depender de los limites de Docker Hub al arrancar)
$imgMysql = "$acrServidor/mysql:8.0"
Invoke-Nativo docker pull --platform linux/amd64 mysql:8.0
Invoke-Nativo docker tag mysql:8.0 $imgMysql
Invoke-Nativo docker push $imgMysql
Remove-Item $fuente -Recurse -Force
Remove-Item $zip -Force

Write-Host "==> 5/7 Entorno de Container Apps" -ForegroundColor Cyan
$envId = az containerapp env list -g $Grupo --query "[?name=='$Entorno'].id" -o tsv
if (-not $envId) {
    Invoke-Az containerapp env create -n $Entorno -g $Grupo -l $Region -o none
    $envId = az containerapp env list -g $Grupo --query "[?name=='$Entorno'].id" -o tsv
}
$dominio = az containerapp env list -g $Grupo --query "[?name=='$Entorno'].properties.defaultDomain" -o tsv
$fqdn = "$App.$dominio"

Write-Host "==> 6/7 Secretos nuevos (MySQL, JWT y cifrado del segundo factor)" -ForegroundColor Cyan
$dbPass = -join ((Get-BytesAleatorios 16) | ForEach-Object { $_.ToString("x2") })
$jwt    = -join ((Get-BytesAleatorios 32) | ForEach-Object { $_.ToString("x2") })
$fernet = [Convert]::ToBase64String((Get-BytesAleatorios 32)).Replace('+', '-').Replace('/', '_')
$acrPass = az acr credential show -n $acr --query "passwords[0].value" -o tsv

# Agente: si en el grupo hay un Azure OpenAI con un modelo desplegado (ver
# activar_llm_azure_openai.ps1), se usa; si no, el motor de reglas.
$proveedor = "reglas"; $llmUrl = ""; $llmModelo = ""; $llmKey = "sin-clave"
$aoai = az cognitiveservices account list -g $Grupo --query "[?kind=='OpenAI'].name | [0]" -o tsv
if ($aoai) {
    $llmModelo = az cognitiveservices account deployment list -n $aoai -g $Grupo --query "[0].name" -o tsv
    if ($llmModelo) {
        $proveedor = "llm"
        $llmUrl = (az cognitiveservices account show -n $aoai -g $Grupo --query properties.endpoint -o tsv).TrimEnd("/") + "/openai/v1"
        $llmKey = az cognitiveservices account keys list -n $aoai -g $Grupo --query key1 -o tsv
        Write-Host "    Agente con LLM: $llmModelo ($aoai)"
    }
}
if ($proveedor -eq "reglas") { Write-Host "    Agente con motor de reglas (no hay Azure OpenAI desplegado)" }

$yaml = (Get-Content (Join-Path $raiz "despliegue\azure\containerapp.plantilla.yaml") -Raw)
$yaml = $yaml.Replace('__REGION__', $Region).Replace('__APP__', $App).Replace('__ENV_ID__', $envId)
$yaml = $yaml.Replace('__ACR_USUARIO__', $acr).Replace('__ACR_PASSWORD__', $acrPass).Replace('__ACR__', $acrServidor)
$yaml = $yaml.Replace('__TAG__', $tag).Replace('__DB_PASSWORD__', $dbPass).Replace('__JWT__', $jwt)
$yaml = $yaml.Replace('__FERNET__', $fernet).Replace('__FQDN__', $fqdn)
$yaml = $yaml.Replace('__AGENTE_PROVEEDOR__', $proveedor).Replace('__LLM_URL__', $llmUrl).Replace('__LLM_MODELO__', $llmModelo).Replace('__LLM_KEY__', $llmKey)
$llmKey = $null
$archivoYaml = Join-Path $env:TEMP "carro-paro-app.yaml"
[IO.File]::WriteAllText($archivoYaml, $yaml)

Write-Host "==> 7/7 Publicacion de la aplicacion" -ForegroundColor Cyan
try {
    $existe = az containerapp list -g $Grupo --query "[?name=='$App'].name" -o tsv
    if ($existe) { Invoke-Az containerapp update -n $App -g $Grupo --yaml $archivoYaml -o none }
    else         { Invoke-Az containerapp create -n $App -g $Grupo --yaml $archivoYaml -o none }
}
finally {
    Remove-Item $archivoYaml -Force -ErrorAction SilentlyContinue   # contiene secretos
}

Write-Host ""
Write-Host "Listo: https://$fqdn" -ForegroundColor Green
Write-Host "La primera carga tarda 5-10 min (descarga de la imagen y creacion de la BD de demostracion)."
Write-Host "Ver logs:  az containerapp logs show -n $App -g $Grupo --container web --follow"
$appId = (az account show --query id -o tsv)
$appId = "/subscriptions/$appId/resourceGroups/$Grupo/providers/Microsoft.App/containerApps/$App"
Write-Host "Apagar:    az rest --method post --uri `"https://management.azure.com$appId/stop?api-version=2024-03-01`""
Write-Host "Encender:  az rest --method post --uri `"https://management.azure.com$appId/start?api-version=2024-03-01`""
