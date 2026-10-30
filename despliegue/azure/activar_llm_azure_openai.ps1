# Activa el agente con LLM (Azure OpenAI) en la Container App carro-paro-web.
# Uso, desde la raiz del repo (con "az login" hecho):
#     Set-ExecutionPolicy -Scope Process Bypass -Force
#     .\despliegue\azure\activar_llm_azure_openai.ps1
# Para volver al motor de reglas:
#     .\despliegue\azure\activar_llm_azure_openai.ps1 -Desactivar
#
# La clave de Azure OpenAI nunca se muestra ni se guarda en archivos: se lee con az
# y se guarda directo como secreto de la Container App.
param(
    [string]$Grupo    = "rg-carro-paro",
    [string]$App      = "carro-paro-web",
    [string]$Recurso  = "carroparo-openai-84669",
    [string]$RegionAI = "eastus",
    [switch]$Desactivar
)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Invoke-Az {
    & az @args
    if ($LASTEXITCODE -ne 0) { throw "Fallo el comando: az $($args -join ' ')" }
}

if ($Desactivar) {
    Write-Host "==> Volviendo al motor de reglas" -ForegroundColor Cyan
    foreach ($c in "web", "api") {
        Invoke-Az containerapp update -n $App -g $Grupo --container-name $c --set-env-vars AGENTE_PROVEEDOR=reglas -o none
    }
    Write-Host "Listo. La app reinicia con el motor de reglas (la BD vuelve a los datos de demostracion)." -ForegroundColor Green
    return
}

Write-Host "==> 1/5 Recurso de Azure OpenAI ($Recurso)" -ForegroundColor Cyan
$existe = az cognitiveservices account list -g $Grupo --query "[?name=='$Recurso'].name" -o tsv
if (-not $existe) {
    Invoke-Az cognitiveservices account create -n $Recurso -g $Grupo -l $RegionAI --kind OpenAI --sku S0 --custom-domain $Recurso --yes -o none
    Write-Host "    Creado."
} else {
    Write-Host "    Ya existe; se reutiliza."
}

Write-Host "==> 2/5 Modelo pequeno disponible" -ForegroundColor Cyan
# Preferencia: modelos pequenos y baratos con soporte de tool-calling
$preferidos = @("gpt-4.1-mini", "gpt-4o-mini", "gpt-5-mini", "gpt-4.1-nano", "gpt-5-nano")
$modelos = az cognitiveservices account list-models -n $Recurso -g $Grupo --query "[?format=='OpenAI'].{n:name, v:version}" -o json | ConvertFrom-Json
$elegido = $null
foreach ($p in $preferidos) {
    $m = $modelos | Where-Object { $_.n -eq $p } | Sort-Object v -Descending | Select-Object -First 1
    if ($m) { $elegido = $m; break }
}
if (-not $elegido) { throw "Ninguno de estos modelos esta disponible en el recurso: $($preferidos -join ', ')" }
$despliegue = $elegido.n
Write-Host "    Modelo: $($elegido.n) version $($elegido.v)"

Write-Host "==> 3/5 Despliegue del modelo (Global Standard, pago por uso)" -ForegroundColor Cyan
$yaDesplegado = az cognitiveservices account deployment list -n $Recurso -g $Grupo --query "[?name=='$despliegue'].name" -o tsv
if (-not $yaDesplegado) {
    & az cognitiveservices account deployment create -n $Recurso -g $Grupo --deployment-name $despliegue `
        --model-format OpenAI --model-name $elegido.n --model-version $elegido.v `
        --sku-name GlobalStandard --sku-capacity 10 -o none
    if ($LASTEXITCODE -ne 0) {
        throw ("No se pudo desplegar el modelo. Si el error habla de cuota (quota) o de la suscripcion, " +
               "la cuenta de prueba no permite Azure OpenAI: copia el mensaje y revisamos la alternativa (Groq/Gemini).")
    }
}

Write-Host "==> 4/5 Prueba directa del modelo" -ForegroundColor Cyan
$endpoint = (az cognitiveservices account show -n $Recurso -g $Grupo --query properties.endpoint -o tsv).TrimEnd("/")
$llmUrl = "$endpoint/openai/v1"
$clave = az cognitiveservices account keys list -n $Recurso -g $Grupo --query key1 -o tsv
$cuerpo = @{ model = $despliegue; messages = @(@{ role = "user"; content = "Responde solo: OK" }) } | ConvertTo-Json -Depth 5
try {
    $r = Invoke-RestMethod -Method Post -Uri "$llmUrl/chat/completions" -ContentType "application/json" `
        -Headers @{ Authorization = "Bearer $clave" } -Body $cuerpo -TimeoutSec 60
    Write-Host "    Respuesta del modelo: $($r.choices[0].message.content)"
} catch {
    throw "La prueba fallo: $($_.Exception.Message). No se modifico la aplicacion."
}

Write-Host "==> 5/5 Configuracion de la Container App (contenedores web y api)" -ForegroundColor Cyan
Invoke-Az containerapp secret set -n $App -g $Grupo --secrets "llm-api-key=$clave" -o none
$clave = $null
foreach ($c in "web", "api") {
    Invoke-Az containerapp update -n $App -g $Grupo --container-name $c --set-env-vars `
        AGENTE_PROVEEDOR=llm "LLM_URL=$llmUrl" "LLM_MODELO=$despliegue" LLM_API_KEY=secretref:llm-api-key LLM_TIMEOUT=60 -o none
}

Write-Host ""
Write-Host "Listo: el agente usa $despliegue en Azure OpenAI." -ForegroundColor Green
Write-Host "La app se reinicia (10 min aprox.) y la BD vuelve a los datos de demostracion."
Write-Host "Si el modelo falla, el agente vuelve solo al motor de reglas."
