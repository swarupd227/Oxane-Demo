<#
.SYNOPSIS
Deploy the workbench to Azure. Run `az login` first. See docs/DEPLOYMENT.md.

.EXAMPLE
./infra/deploy.ps1 -ResourceGroup rg-oxane-workbench -Location eastus2 `
    -AnalystUsers "analyst@contoso.com" -ApproverUsers "reviewer@contoso.com"
#>
param(
    [Parameter(Mandatory)] [string] $ResourceGroup,
    [Parameter(Mandatory)] [string] $Location,
    [Parameter(Mandatory)] [string] $AnalystUsers,
    [Parameter(Mandatory)] [string] $ApproverUsers,
    [string] $Tag = (git rev-parse --short HEAD),
    [string] $FoundryResource = "",
    [string] $FoundryApiKey = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$template = Join-Path $PSScriptRoot "main.bicep"

function Deploy-Template([string[]] $Extra) {
    $result = az deployment group create --resource-group $ResourceGroup --template-file $template `
        --parameters postgresPassword=$postgresPassword $Extra --query properties.outputs --output json
    return ($result | ConvertFrom-Json)
}

az group create --name $ResourceGroup --location $Location --output none

# Reuse the stored password on a repeat deployment, so the database keeps working.
$generated = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
$postgresPassword = $env:OXANE_POSTGRES_PASSWORD
if (-not $postgresPassword) {
    $postgresPassword = "Wb1$generated"
    Write-Host "Save this for later deployments as OXANE_POSTGRES_PASSWORD: $postgresPassword"
}

Write-Host "Creating the registry, database, vault and environment"
$foundation = Deploy-Template @()

Write-Host "Building the image in Azure"
$repository = "workbench:$Tag"
az acr build --registry $foundation.registryName.value --image $repository `
    --file (Join-Path $PSScriptRoot ".." "Dockerfile") (Join-Path $PSScriptRoot "..") --output none
$image = "$($foundation.registryServer.value)/$repository"

Write-Host "Registering sign-in with Entra"
$redirect = "$($foundation.appUrl.value)/.auth/login/aad/callback"
$clientId = az ad app list --display-name "Onboarding Workbench" --query "[0].appId" --output tsv
if (-not $clientId) {
    $clientId = az ad app create --display-name "Onboarding Workbench" `
        --sign-in-audience AzureADMyOrg --web-redirect-uris $redirect `
        --enable-id-token-issuance true --query appId --output tsv
}
$clientSecret = az ad app credential reset --id $clientId --display-name "workbench" `
    --years 1 --query password --output tsv

Write-Host "Deploying the app"
$outputs = Deploy-Template @(
    "image=$image", "authClientId=$clientId", "authClientSecret=$clientSecret",
    "analystUsers=$AnalystUsers", "approverUsers=$ApproverUsers",
    "foundryResource=$FoundryResource", "foundryApiKey=$FoundryApiKey"
)
Write-Host "Done: $($outputs.appUrl.value)"
