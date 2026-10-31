# Despliega SMARTDATA 360 - Carro de Paro en Azure Container Apps (HTTPS incluido),
# con la base de datos en Azure Database for MySQL (servidor flexible): los datos y
# las cuentas se conservan al detener, reiniciar o publicar una version nueva.
#
# Requisitos: Azure CLI (winget install -e --id Microsoft.AzureCLI), "az login" y
# Docker Desktop encendido (las imagenes se construyen en este equipo: las cuentas de
# prueba de Azure no permiten ACR Tasks / az acr build).
# Uso, desde la raiz del repo en PowerShell:
#     Set-ExecutionPolicy -Scope Process Bypass -Force
#     .\despliegue\azure\desplegar_containerapps.ps1
# Se puede volver a ejecutar para publicar una version nueva (usa el ultimo commit).
#
# Region: eastus. En la cuenta de prueba, Brazil South no permite el servidor MySQL, y
# la app va en la misma region que la base de datos para no sumar latencia a cada consulta.
param(
    [string]$Grupo        = "rg-carro-paro",
    [string]$Region       = "eastus",
    [string]$Entorno      = "cae-carro-paro-eastus",
    [string]$App          = "carro-paro-web",
    [string]$ServidorBD   = "",            # vacio = carroparo-mysql-<numero del registro>
    [string]$UsuarioBD    = "carroadmin"
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
function New-Hex([int]$n) { -join ((Get-BytesAleatorios $n) | ForEach-Object { $_.ToString("x2") }) }
function Test-ClaveMysql([string]$c) {
    # Azure exige 8+ caracteres con 3 de 4 tipos (mayuscula, minuscula, numero, simbolo)
    return $c -and $c.Length -ge 12 -and $c -cmatch '[A-Z]' -and $c -cmatch '[a-z]' -and
           $c -match '\d' -and $c -match '[^A-Za-z0-9]'
}

$raiz = (git rev-parse --show-toplevel)
Set-Location $raiz
if (git status --porcelain) {
    Write-Warning "Hay cambios sin commit: la imagen se construye con el ultimo commit (HEAD), no con ellos."
}
$tag = (git rev-parse --short HEAD)

Write-Host "==> 1/9 Extension de Container Apps y proveedor de MySQL" -ForegroundColor Cyan
Invoke-Az extension add --name containerapp --upgrade --only-show-errors
Invoke-Az provider register --namespace Microsoft.DBforMySQL --wait -o none

Write-Host "==> 2/9 Grupo de recursos $Grupo" -ForegroundColor Cyan
if ((az group exists --name $Grupo) -ne "true") {
    Invoke-Az group create --name $Grupo --location $Region -o none
} else {
    Write-Host "    El grupo ya existe; se reutiliza (los recursos nuevos van en $Region)."
}

Write-Host "==> 3/9 Registro de contenedores (ACR Basic)" -ForegroundColor Cyan
$acr = az acr list -g $Grupo --query "[0].name" -o tsv
if (-not $acr) {
    $acr = "carroparo" + (Get-Random -Minimum 10000 -Maximum 99999)
    Invoke-Az acr create -g $Grupo -n $acr --sku Basic --admin-enabled true -l $Region -o none
}
$acrServidor = "$acr.azurecr.io"
if (-not $ServidorBD) { $ServidorBD = "carroparo-mysql-" + ($acr -replace '\D', '') }
Write-Host "    Registro: $acrServidor"

Write-Host "==> 4/9 Construccion local y subida de imagenes" -ForegroundColor Cyan
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
Remove-Item $fuente -Recurse -Force
Remove-Item $zip -Force

Write-Host "==> 5/9 Secretos (se conservan entre despliegues)" -ForegroundColor Cyan
# Con datos persistentes, los secretos NO pueden cambiar en cada despliegue: otra clave de
# cifrado dejaria ilegibles los segundos factores guardados y otra contrasena dejaria a la
# app sin acceso a la BD. Se reutilizan, en este orden: copia local, app existente, nuevos.
$carpetaSecretos = Join-Path $env:USERPROFILE ".carro-paro-azure"
$archivoSecretos = Join-Path $carpetaSecretos "secretos.json"     # fuera del repo: nunca va a Git
$sec = @{}
if (Test-Path $archivoSecretos) {
    (Get-Content $archivoSecretos -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $sec[$_.Name] = $_.Value }
    Write-Host "    Reutilizando secretos guardados en $archivoSecretos"
}
$appActual = az containerapp list -g $Grupo --query "[?name=='$App'] | [0].{loc:location, env:properties.managedEnvironmentId}" -o json | ConvertFrom-Json
if ($appActual) {
    $enApp = az containerapp secret list -n $App -g $Grupo --show-values -o json | ConvertFrom-Json
    foreach ($s in $enApp) {
        $mapa = @{ "jwt-secreto" = "jwt"; "clave-cifrado" = "fernet"; "db-password" = "db" }
        $clave = $mapa[$s.name]
        if ($clave -and -not $sec[$clave]) { $sec[$clave] = $s.value }
    }
}
$dbNueva = $false
if (-not $sec["jwt"])    { $sec["jwt"] = New-Hex 32 }
if (-not $sec["fernet"]) { $sec["fernet"] = [Convert]::ToBase64String((Get-BytesAleatorios 32)).Replace('+', '-').Replace('/', '_') }
if (-not (Test-ClaveMysql $sec["db"])) { $sec["db"] = "Cp#" + (New-Hex 16) + "Z9"; $dbNueva = $true }
New-Item -ItemType Directory -Force $carpetaSecretos | Out-Null
($sec | ConvertTo-Json) | Set-Content -Path $archivoSecretos -Encoding UTF8
Write-Host "    Copia de seguridad de los secretos: $archivoSecretos (no la borres ni la subas a Git)"

Write-Host "==> 6/9 Base de datos persistente: $ServidorBD ($Region)" -ForegroundColor Cyan
$bdExiste = az mysql flexible-server list -g $Grupo --query "[?name=='$ServidorBD'].name" -o tsv
if (-not $bdExiste) {
    Write-Host "    Creando el servidor MySQL (B1ms, 20 GB; 5-10 min). Entra en los servicios gratuitos de la cuenta."
    # --public-access 0.0.0.0: solo admite conexiones desde servicios de Azure (no desde internet en general)
    Invoke-Az mysql flexible-server create -g $Grupo -n $ServidorBD -l $Region `
        --tier Burstable --sku-name Standard_B1ms --storage-size 20 --version 8.0.21 `
        --admin-user $UsuarioBD --admin-password $sec["db"] --public-access 0.0.0.0 `
        --database-name carro_paro_db --high-availability Disabled --backup-retention 7 --yes -o none
} elseif ($dbNueva) {
    Write-Host "    El servidor ya existe pero no habia contrasena guardada: se le asigna la nueva."
    Invoke-Az mysql flexible-server update -g $Grupo -n $ServidorBD --admin-password $sec["db"] -o none
} else {
    Write-Host "    El servidor ya existe; se reutiliza con sus datos."
}
$dbHost = az mysql flexible-server show -g $Grupo -n $ServidorBD --query fullyQualifiedDomainName -o tsv

Write-Host "==> 7/9 Traslado desde la region anterior (si aplica)" -ForegroundColor Cyan
if ($appActual -and (($appActual.loc -replace '\s', '').ToLower() -ne $Region.ToLower())) {
    $envViejo = ($appActual.env -split '/')[-1]
    Write-Host "    La app estaba en $($appActual.loc): se elimina para crearla en $Region (sus datos eran temporales)."
    Invoke-Az containerapp delete -n $App -g $Grupo --yes -o none
    $otras = az containerapp list -g $Grupo --query "[?properties.managedEnvironmentId=='$($appActual.env)'].name" -o tsv
    if (-not $otras) {
        Write-Host "    Eliminando el entorno anterior $envViejo (en segundo plano)."
        Invoke-Az containerapp env delete -n $envViejo -g $Grupo --yes --no-wait -o none
    }
} else {
    Write-Host "    No hace falta."
}

Write-Host "==> 8/9 Entorno de Container Apps ($Region)" -ForegroundColor Cyan
$envId = az containerapp env list -g $Grupo --query "[?name=='$Entorno'].id" -o tsv
if (-not $envId) {
    Invoke-Az containerapp env create -n $Entorno -g $Grupo -l $Region -o none
    $envId = az containerapp env list -g $Grupo --query "[?name=='$Entorno'].id" -o tsv
}
$dominio = az containerapp env list -g $Grupo --query "[?name=='$Entorno'].properties.defaultDomain" -o tsv
$fqdn = "$App.$dominio"
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
$yaml = $yaml.Replace('__TAG__', $tag).Replace('__DB_PASSWORD__', $sec["db"]).Replace('__JWT__', $sec["jwt"])
$yaml = $yaml.Replace('__FERNET__', $sec["fernet"]).Replace('__FQDN__', $fqdn)
$yaml = $yaml.Replace('__DB_HOST__', $dbHost).Replace('__DB_USER__', $UsuarioBD)
$yaml = $yaml.Replace('__AGENTE_PROVEEDOR__', $proveedor).Replace('__LLM_URL__', $llmUrl).Replace('__LLM_MODELO__', $llmModelo).Replace('__LLM_KEY__', $llmKey)
$llmKey = $null
$archivoYaml = Join-Path $env:TEMP "carro-paro-app.yaml"
[IO.File]::WriteAllText($archivoYaml, $yaml)

Write-Host "==> 9/9 Publicacion de la aplicacion" -ForegroundColor Cyan
try {
    $existe = az containerapp list -g $Grupo --query "[?name=='$App'].name" -o tsv
    if ($existe) { Invoke-Az containerapp update -n $App -g $Grupo --yaml $archivoYaml -o none }
    else         { Invoke-Az containerapp create -n $App -g $Grupo --yaml $archivoYaml -o none }
}
finally {
    Remove-Item $archivoYaml -Force -ErrorAction SilentlyContinue   # contiene secretos
}

$sub = (az account show --query id -o tsv)
$appId = "/subscriptions/$sub/resourceGroups/$Grupo/providers/Microsoft.App/containerApps/$App"
Write-Host ""
Write-Host "Listo: https://$fqdn" -ForegroundColor Green
Write-Host "La primera carga tarda 5-10 min. Los datos ahora se conservan en $ServidorBD."
Write-Host "Ver logs:  az containerapp logs show -n $App -g $Grupo --container web --follow"
Write-Host "Apagar app:        az rest --method post --uri `"https://management.azure.com$appId/stop?api-version=2024-03-01`""
Write-Host "Encender app:      az rest --method post --uri `"https://management.azure.com$appId/start?api-version=2024-03-01`""
Write-Host "Apagar/encender BD (opcional): az mysql flexible-server stop|start -g $Grupo -n $ServidorBD"
