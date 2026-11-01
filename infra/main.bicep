// The onboarding workbench on Azure: one container, PostgreSQL, Key Vault and Entra sign-in.
// Deploy with infra/deploy.ps1, which runs this twice: first without an image, so the
// registry exists to build into, then with the image and sign-in settings.

targetScope = 'resourceGroup'

@description('Azure region for everything except where a service is not offered.')
param location string = resourceGroup().location

@description('Short lowercase prefix for resource names.')
@maxLength(16)
param name string = 'oxaneworkbench'

@secure()
@description('PostgreSQL administrator password. The deploy script generates it.')
param postgresPassword string

@description('Image to run, such as myregistry.azurecr.io/workbench:v1. Empty skips the app.')
param image string = ''

@description('Entra application (client) ID for sign-in. Empty leaves the app unreachable.')
param authClientId string = ''

@secure()
@description('Entra client secret for sign-in.')
param authClientSecret string = ''

@description('Comma-separated sign-in names of onboarding analysts.')
param analystUsers string = ''

@description('Comma-separated sign-in names of second analysts.')
param approverUsers string = ''

@allowed(['anthropic', 'foundry'])
param llmProvider string = 'foundry'

@secure()
@description('Claude on Foundry API key. Only live runs use it. Replay needs no key.')
param foundryApiKey string = ''

@description('Claude on Foundry resource name.')
param foundryResource string = ''

var suffix = uniqueString(resourceGroup().id)
var deployApp = !empty(image)
var signInConfigured = !empty(authClientId)
var hasFoundry = !empty(foundryApiKey)
var postgresUser = 'workbench'
var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${name}${suffix}'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-identity'
  location: location
}

resource pullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPull)
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('${name}${suffix}', 24)
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
  }
}

resource vaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, keyVaultSecretsUser)
  scope: vault
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${name}-${suffix}'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: postgresUser
    administratorLoginPassword: postgresPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: 'oxane'
}

// Reachable from Azure services only. The address 0.0.0.0 is Azure's marker for that rule.
resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource databaseSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'database-url'
  properties: {
    value: 'postgresql+psycopg://${postgresUser}:${postgresPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/oxane?sslmode=require'
  }
}

resource signInSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (signInConfigured) {
  parent: vault
  name: 'auth-client-secret'
  properties: { value: authClientSecret }
}

resource foundrySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (hasFoundry) {
  parent: vault
  name: 'foundry-api-key'
  properties: { value: foundryApiKey }
}

resource appEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = if (deployApp) {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  dependsOn: [pullRole, vaultRole, database, allowAzure]
  properties: {
    managedEnvironmentId: appEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
      secrets: concat(
        [{ name: 'database-url', keyVaultUrl: databaseSecret.properties.secretUri, identity: identity.id }],
        signInConfigured
          ? [{ name: 'auth-client-secret', keyVaultUrl: '${vault.properties.vaultUri}secrets/auth-client-secret', identity: identity.id }]
          : [],
        hasFoundry
          ? [{ name: 'foundry-api-key', keyVaultUrl: '${vault.properties.vaultUri}secrets/foundry-api-key', identity: identity.id }]
          : []
      )
    }
    template: {
      // One always-on replica: no cold start on stage, and the app holds no shared cache.
      scale: { minReplicas: 1, maxReplicas: 1 }
      containers: [
        {
          name: 'workbench'
          image: image
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: concat(
            [
              { name: 'DATABASE_URL', secretRef: 'database-url' }
              { name: 'AUTH_REQUIRED', value: 'true' }
              { name: 'ANALYST_USERS', value: analystUsers }
              { name: 'APPROVER_USERS', value: approverUsers }
              { name: 'LLM_PROVIDER', value: llmProvider }
              { name: 'ANTHROPIC_FOUNDRY_RESOURCE', value: foundryResource }
            ],
            hasFoundry ? [{ name: 'ANTHROPIC_FOUNDRY_API_KEY', secretRef: 'foundry-api-key' }] : []
          )
          probes: [
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000 }
              periodSeconds: 10
            }
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
          ]
        }
      ]
    }
  }
}

// Sign-in sits in front of the container, which is what makes the identity header trustworthy.
resource signIn 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (deployApp && signInConfigured) {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: ['/api/health']
    }
    identityProviders: {
      azureActiveDirectory: {
        registration: {
          clientId: authClientId
          clientSecretSettingName: 'auth-client-secret'
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
      }
    }
  }
}

output registryName string = registry.name
output registryServer string = registry.properties.loginServer
output appUrl string = 'https://${name}.${appEnvironment.properties.defaultDomain}'
output resourceGroupName string = resourceGroup().name
