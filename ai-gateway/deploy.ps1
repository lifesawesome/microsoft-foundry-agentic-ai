<#
.SYNOPSIS
    Deploys the Foundry AI Gateway (Azure API Management + Azure Managed Redis)
    into the demoaifoundry resource group and writes connection details to .env.

.NOTES
    APIM Basic v2 + Azure Managed Redis take ~20-40 minutes to provision.
#>
[CmdletBinding()]
param(
    [string]$ResourceGroup = 'demoaifoundry',
    [string]$Location = 'westus',
    [string]$FoundryAccountName = 'demopocaifoundry',
    [string]$EmbeddingsDeployment = 'text-embedding-3-small',
    [int]$TokensPerMinute = 1000,
    [string]$ScoreThreshold = '0.2',
    [string]$PublisherEmail
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $PublisherEmail) {
    $PublisherEmail = az account show --query 'user.name' -o tsv
}

Write-Host "Deploying AI Gateway into '$ResourceGroup' ($Location)..." -ForegroundColor Cyan
Write-Host "Publisher email: $PublisherEmail" -ForegroundColor DarkGray

$deployName = "ai-gateway-$(Get-Date -Format 'yyyyMMddHHmmss')"

$outputs = az deployment group create `
    --resource-group $ResourceGroup `
    --name $deployName `
    --template-file (Join-Path $here 'infra/main.bicep') `
    --parameters `
        location=$Location `
        foundryAccountName=$FoundryAccountName `
        embeddingsDeploymentName=$EmbeddingsDeployment `
        tokensPerMinute=$TokensPerMinute `
        semanticCacheScoreThreshold=$ScoreThreshold `
        publisherEmail=$PublisherEmail `
    --query properties.outputs -o json | ConvertFrom-Json

if (-not $outputs) { throw 'Deployment returned no outputs.' }

$gatewayUrl = $outputs.gatewayUrl.value
$apimName   = $outputs.apimName.value
$subKey     = $outputs.subscriptionKey.value

$envPath = Join-Path $here '.env'
@(
    "AI_GATEWAY_URL=$gatewayUrl"
    "AI_GATEWAY_KEY=$subKey"
    "AI_GATEWAY_APIM_NAME=$apimName"
    "AI_GATEWAY_RG=$ResourceGroup"
) | Set-Content -Path $envPath -Encoding utf8

Write-Host "`nDeployment complete." -ForegroundColor Green
Write-Host "Gateway URL : $gatewayUrl"
Write-Host "APIM name   : $apimName"
Write-Host "Details written to $envPath (git-ignored)."
Write-Host "`nRun the demo:  python test/demo.py" -ForegroundColor Yellow
