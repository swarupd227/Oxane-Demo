<#
.SYNOPSIS
Deploy the workbench (onboarding and monitoring) to Azure. Run `az login` first.
See docs/DEPLOYMENT.md.

.EXAMPLE
./infra/deploy.ps1 -Subscription "My subscription" -ResourceGroup rg-oxane-workbench -Location eastus2 `
    -AnalystUsers "analyst@contoso.com" -ApproverUsers "reviewer@contoso.com"
#>
param(
    [Parameter(Mandatory)] [string] $ResourceGroup,
    [Parameter(Mandatory)] [string] $Location,
    # PostgreSQL's region, if the main one does not offer its SKU to this subscription.
    [string] $PostgresLocation = "",
    # Who may act once sign-in is on. Not needed with -NoSignIn.
    [string] $AnalystUsers = "",
    # The second analysts. Leave empty to deploy before a second person is known: everything but
    # approval then works, and approval waits until someone is added here and redeployed.
    [string] $ApproverUsers = "",
    # Heads of monitoring: the third approval level for clients that require one (Thornbury).
    [string] $SeniorUsers = "",
    # Defaults to the CLI's current subscription.
    [string] $Subscription = "",
    [string] $Tag = (git rev-parse --short HEAD),
    # Build with local Docker and push, for subscriptions where ACR Tasks (az acr build) are blocked.
    [switch] $LocalBuild,
    # Deploy the image already in the registry under -Tag, without building.
    [switch] $SkipBuild,
    # Database on the server; a new name gives the app a fresh, empty database.
    [string] $DatabaseName = "oxane",
    # Demo mode: no Entra sign-in, so anyone with the address can open it and pick who they act as
    # in the app, as when it runs locally. Only for synthetic demo data.
    [switch] $NoSignIn,
    # An Entra app registration made by an administrator, when you may not register one yourself.
    # Its redirect address must be <app address>/.auth/login/aad/callback, which this script prints.
    [string] $AuthClientId = "",
    [string] $AuthClientSecret = "",
    # Live AI for new cases: reads ANTHROPIC_API_KEY from the environment or the git-ignored .env,
    # and a demo access code from OXANE_DEMO_ACCESS_CODE or .env.azure (a new one is saved there).
    [switch] $LiveAi,
    [string] $LiveDailyCapUsd = "10",
    [string] $FoundryResource = "",
    [string] $FoundryApiKey = "",
    # After deploying, run the browser suite's Azure project (tests/e2e, `--project=azure`) against
    # the new app. Needs Node.js and the e2e packages; demo mode (-NoSignIn) only.
    [switch] $SmokeTest
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$root = Join-Path $PSScriptRoot ".."
$template = Join-Path $PSScriptRoot "main.bicep"
$passwordFile = Join-Path $root ".env.azure"
$databaseLocation = if ($PostgresLocation) { $PostgresLocation } else { $Location }
$sub = if ($Subscription) { @("--subscription", $Subscription) } else { @() }

function Deploy-Template([string[]] $Extra) {
    $result = az deployment group create @sub --resource-group $ResourceGroup --template-file $template `
        --parameters postgresPassword=$postgresPassword postgresLocation=$databaseLocation databaseName=$DatabaseName $Extra --query properties.outputs --output json
    return ($result | ConvertFrom-Json)
}

az group create @sub --name $ResourceGroup --location $Location --output none

# Reuse the stored password on a repeat deployment, so the database keeps working. It comes from
# OXANE_POSTGRES_PASSWORD, or from .env.azure (git-ignored), and a new one is saved there.
$postgresPassword = $env:OXANE_POSTGRES_PASSWORD
if (-not $postgresPassword -and (Test-Path $passwordFile)) {
    $line = Get-Content $passwordFile | Where-Object { $_ -match '^OXANE_POSTGRES_PASSWORD=' } | Select-Object -First 1
    if ($line) { $postgresPassword = $line.Substring('OXANE_POSTGRES_PASSWORD='.Length).Trim() }
}
if (-not $postgresPassword) {
    $generated = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
    $postgresPassword = "Wb1$generated"
    Add-Content -Path $passwordFile -Value "OXANE_POSTGRES_PASSWORD=$postgresPassword"
    Write-Host "Saved a new database password to $passwordFile. Keep it for later deployments."
}

Write-Host "Creating the registry, database, vault and environment"
$foundation = Deploy-Template @()

$repository = "workbench:$Tag"
$image = "$($foundation.registryServer.value)/$repository"
if ($SkipBuild) {
    Write-Host "Using the existing image $image"
} elseif ($LocalBuild) {
    Write-Host "Building the image locally and pushing it"
    docker build --tag $image --file (Join-Path $root "Dockerfile") $root
    az acr login @sub --name $foundation.registryName.value
    docker push $image
} else {
    # Streamed build logs can stop `az acr build` on a Windows console, so queue it and poll.
    Write-Host "Building the image in Azure"
    $runId = az acr build @sub --registry $foundation.registryName.value --image $repository `
        --file (Join-Path $root "Dockerfile") $root --no-logs --query runId --output tsv
    do {
        Start-Sleep -Seconds 20
        $state = az acr task show-run @sub --registry $foundation.registryName.value `
            --run-id $runId --query status --output tsv
    } while ($state -in @("Queued", "Started", "Running"))
    if ($state -ne "Succeeded") {
        throw "Image build $runId ended as $state. See: az acr task logs --registry $($foundation.registryName.value) --run-id $runId"
    }
}

if ($NoSignIn) {
    Write-Host "Demo mode: no sign-in. Anyone with the address can open the app."
    $clientId = ""; $clientSecret = ""
} else {
if (-not $AnalystUsers) { throw "Pass -AnalystUsers, or -NoSignIn for demo mode." }
Write-Host "Registering sign-in with Entra"
$appName = "Oxane Workbench"
$redirect = "$($foundation.appUrl.value)/.auth/login/aad/callback"
Write-Host "Sign-in redirect address: $redirect"
if ($AuthClientId) {
    # An administrator registered the application (for users who may not register one).
    $clientId = $AuthClientId
    $clientSecret = if ($AuthClientSecret) { $AuthClientSecret } else { $env:OXANE_AUTH_CLIENT_SECRET }
    if (-not $clientSecret) { throw "Pass -AuthClientSecret or set OXANE_AUTH_CLIENT_SECRET with -AuthClientId." }
} else {
    $clientId = az ad app list --display-name $appName --query "[0].appId" --output tsv
    if (-not $clientId) {
        $clientId = az ad app create --display-name $appName `
            --sign-in-audience AzureADMyOrg --web-redirect-uris $redirect `
            --enable-id-token-issuance true --query appId --output tsv
    } else {
        az ad app update --id $clientId --web-redirect-uris $redirect --enable-id-token-issuance true
    }
    # The enterprise application, so people in the organisation can sign in to it.
    if (-not (az ad sp list --filter "appId eq '$clientId'" --query "[0].id" --output tsv)) {
        az ad sp create --id $clientId --output none
    }
    $clientSecret = az ad app credential reset --id $clientId --display-name "workbench" `
        --years 1 --query password --output tsv --only-show-errors
}

}

function Read-EnvValue([string] $File, [string] $Name) {
    if (-not (Test-Path $File)) { return "" }
    $line = Get-Content $File | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if ($line) { return $line.Substring($Name.Length + 1).Trim().Trim('"') }
    return ""
}
$liveParams = @()
if ($LiveAi) {
    $anthropicKey = if ($env:ANTHROPIC_API_KEY) { $env:ANTHROPIC_API_KEY } else { Read-EnvValue (Join-Path $root ".env") "ANTHROPIC_API_KEY" }
    # The key may instead be entered later by an admin in Settings > AI provider.
    if (-not $anthropicKey) { Write-Host "No ANTHROPIC_API_KEY found; an admin can set it in Settings > AI provider." }
    $accessCode = if ($env:OXANE_DEMO_ACCESS_CODE) { $env:OXANE_DEMO_ACCESS_CODE } else { Read-EnvValue $passwordFile "OXANE_DEMO_ACCESS_CODE" }
    if (-not $accessCode) {
        $accessCode = "oxane-" + ([Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(3))).ToLower()
        Add-Content -Path $passwordFile -Value "OXANE_DEMO_ACCESS_CODE=$accessCode"
        Write-Host "Saved a new demo access code to $passwordFile."
    }
    $liveParams = @("llmProvider=anthropic", "anthropicApiKey=$anthropicKey", "demoAccessCode=$accessCode", "liveDailyCapUsd=$LiveDailyCapUsd")
}

# Encrypts settings saved in the app (an admin-entered model key). Kept in .env.azure so a
# redeploy can still read what was saved.
$settingsKey = if ($env:OXANE_SETTINGS_ENCRYPTION_KEY) { $env:OXANE_SETTINGS_ENCRYPTION_KEY } else { Read-EnvValue $passwordFile "OXANE_SETTINGS_ENCRYPTION_KEY" }
if (-not $settingsKey) {
    $settingsKey = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('+', '-').Replace('/', '_')
    Add-Content -Path $passwordFile -Value "OXANE_SETTINGS_ENCRYPTION_KEY=$settingsKey"
    Write-Host "Saved a new settings encryption key to $passwordFile. Keep it: saved settings need it."
}
$liveParams += @("settingsEncryptionKey=$settingsKey")

Write-Host "Deploying the app"
$appParams = @(
    "image=$image", "authClientId=$clientId", "authClientSecret=$clientSecret",
    "analystUsers=$AnalystUsers", "approverUsers=$ApproverUsers", "seniorUsers=$SeniorUsers",
    "foundryResource=$FoundryResource", "foundryApiKey=$FoundryApiKey"
) + $liveParams
$outputs = Deploy-Template $appParams
Write-Host "Done: $($outputs.appUrl.value)"

if ($SmokeTest) {
    if (-not $NoSignIn) {
        Write-Warning "Skipping the smoke test: it acts as each persona, which needs demo mode (-NoSignIn)."
    } else {
        Write-Host "Smoke test: the browser suite's Azure project against $($outputs.appUrl.value)"
        $e2e = Join-Path $root "tests/e2e"
        $env:BASE_URL = $outputs.appUrl.value
        $env:NEWDEALS_DIR = Join-Path $root "deal-kit/output/newdeals"
        if (-not $env:DEMO_ACCESS_CODE) {
            $env:DEMO_ACCESS_CODE = if ($accessCode) { $accessCode } else { Read-EnvValue $passwordFile "OXANE_DEMO_ACCESS_CODE" }
        }
        Push-Location $e2e
        try {
            if (-not (Test-Path (Join-Path $e2e "node_modules/@playwright/test"))) { npm ci }
            npx playwright install chromium
            # A new revision can take a minute to serve; wait for its health check first.
            $healthy = $false
            for ($i = 0; $i -lt 30 -and -not $healthy; $i++) {
                try { $healthy = (Invoke-WebRequest "$($env:BASE_URL)/api/health" -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200 } catch { Start-Sleep -Seconds 10 }
            }
            if (-not $healthy) { throw "The app did not answer $($env:BASE_URL)/api/health" }
            npx playwright test --project=azure
        } finally {
            Pop-Location
        }
        Write-Host "Smoke test passed."
    }
}
