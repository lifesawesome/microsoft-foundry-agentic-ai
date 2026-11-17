// ---------------------------------------------------------------------------
// AI Gateway for Microsoft Foundry
// Azure API Management (Basic v2) in front of an existing Foundry resource,
// demonstrating: token limiting (TPM + quota), token metrics, semantic caching
// (Azure Managed Redis + embeddings), and managed-identity backend auth.
// ---------------------------------------------------------------------------

@description('Location for the new resources. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Name of the EXISTING Microsoft Foundry (AI Services) account to govern.')
param foundryAccountName string = 'demopocaifoundry'

@description('Name of the API Management (AI Gateway) instance to create.')
param apimName string = 'apim-aigw-${uniqueString(resourceGroup().id)}'

@description('APIM publisher email (required by APIM).')
param publisherEmail string

@description('APIM publisher / organization display name.')
param publisherName string = 'Foundry AI Gateway Demo'

@description('Azure Managed Redis instance name that backs the semantic cache.')
param redisName string = 'amr-aigw-${uniqueString(resourceGroup().id)}'

@description('Log Analytics workspace name for gateway request logs (ApiManagementGatewayLogs).')
param logAnalyticsName string = 'law-aigw-${uniqueString(resourceGroup().id)}'

@description('Embeddings deployment used to generate vectors for semantic caching.')
param embeddingsDeploymentName string = 'text-embedding-3-small'

@description('Tokens-per-minute limit used for the demo (high enough for normal traffic; a concurrent burst exceeds it).')
param tokensPerMinute int = 1000

@description('Semantic cache distance threshold (0.0-1.0). Lower = stricter. >0.2 risks false matches.')
param semanticCacheScoreThreshold string = '0.2'

@description('Azure OpenAI data-plane API version exposed through the gateway.')
param openAiApiVersion string = '2024-10-21'

// ---- Existing Foundry account -----------------------------------------------
resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: foundryAccountName
}

var foundryEndpoint = foundry.properties.endpoint // https://<name>.cognitiveservices.azure.com/

// ---- Azure Managed Redis (RediSearch = vector store for semantic cache) ------
resource redis 'Microsoft.Cache/redisEnterprise@2024-10-01' = {
  name: redisName
  location: location
  sku: {
    name: 'Balanced_B0'
  }
}

resource redisDb 'Microsoft.Cache/redisEnterprise/databases@2024-10-01' = {
  parent: redis
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    clusteringPolicy: 'EnterpriseCluster'
    evictionPolicy: 'NoEviction'
    port: 10000
    modules: [
      {
        name: 'RediSearch'
      }
    ]
  }
}

// ---- API Management (the AI Gateway) ----------------------------------------
resource apim 'Microsoft.ApiManagement/service@2024-06-01-preview' = {
  name: apimName
  location: location
  sku: {
    name: 'BasicV2'
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

// ---- Grant APIM's managed identity access to the Foundry account -------------
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
resource foundryRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, apim.id, cognitiveServicesUserRoleId)
  scope: foundry
  properties: {
    principalId: apim.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ---- Backends ---------------------------------------------------------------
resource openaiBackend 'Microsoft.ApiManagement/service/backends@2024-06-01-preview' = {
  parent: apim
  name: 'openai-backend'
  properties: {
    protocol: 'http'
    url: '${foundryEndpoint}openai'
  }
}

resource embeddingsBackend 'Microsoft.ApiManagement/service/backends@2024-06-01-preview' = {
  parent: apim
  name: 'embeddings-backend'
  properties: {
    protocol: 'http'
    url: '${foundryEndpoint}openai/deployments/${embeddingsDeploymentName}/embeddings'
  }
}

// ---- External cache (Redis) that APIM uses for semantic caching --------------
resource apimCache 'Microsoft.ApiManagement/service/caches@2024-06-01-preview' = {
  parent: apim
  name: 'default'
  properties: {
    connectionString: '${redis.properties.hostName}:10000,password=${redisDb.listKeys().primaryKey},ssl=True,abortConnect=False'
    useFromLocation: 'default'
    description: redis.name
  }
}

// ---- Azure OpenAI API imported from the official OpenAPI spec -----------------
resource openaiApi 'Microsoft.ApiManagement/service/apis@2024-06-01-preview' = {
  parent: apim
  name: 'azure-openai-api'
  properties: {
    displayName: 'Azure OpenAI (via AI Gateway)'
    apiType: 'http'
    path: 'openai'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'api-key'
    }
    format: 'openapi-link'
    value: 'https://raw.githubusercontent.com/Azure/azure-rest-api-specs/main/specification/cognitiveservices/data-plane/AzureOpenAI/inference/stable/${openAiApiVersion}/inference.json'
    serviceUrl: '${foundryEndpoint}openai'
  }
}

// ---- Gateway policy: cache -> token limit -> metrics -> MI auth ---------------
var policyXml = replace(replace(loadTextContent('../policies/ai-gateway-policy.xml'), '__TPM__', string(tokensPerMinute)), '__SCORE__', semanticCacheScoreThreshold)
resource openaiApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-06-01-preview' = {
  parent: openaiApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: policyXml
  }
  dependsOn: [
    openaiBackend
    embeddingsBackend
    apimCache
  ]
}

// ---- Product + subscription so the demo has a usable api-key -----------------
resource product 'Microsoft.ApiManagement/service/products@2024-06-01-preview' = {
  parent: apim
  name: 'ai-gateway'
  properties: {
    displayName: 'AI Gateway'
    description: 'Foundry models governed by the AI Gateway.'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

resource productApiLink 'Microsoft.ApiManagement/service/products/apis@2024-06-01-preview' = {
  parent: product
  name: openaiApi.name
}

resource subscription 'Microsoft.ApiManagement/service/subscriptions@2024-06-01-preview' = {
  parent: apim
  name: 'ai-gateway-demo'
  properties: {
    displayName: 'AI Gateway Demo Subscription'
    scope: product.id
    state: 'active'
  }
}

// ---- Observability: Log Analytics + gateway request logs --------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// The 'azuremonitor' logger is auto-created; reference it to enable request logging.
resource azureMonitorLogger 'Microsoft.ApiManagement/service/loggers@2024-06-01-preview' existing = {
  parent: apim
  name: 'azuremonitor'
}

// Log 100% of requests (with error detail) into the Azure Monitor pipeline.
resource apimAzureMonitorDiagnostic 'Microsoft.ApiManagement/service/diagnostics@2024-06-01-preview' = {
  parent: apim
  name: 'azuremonitor'
  properties: {
    loggerId: azureMonitorLogger.id
    alwaysLog: 'allErrors'
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    verbosity: 'information'
  }
  dependsOn: [
    openaiApiPolicy
  ]
}

// Export GatewayLogs (and metrics) to the workspace as resource-specific tables.
resource apimDiagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'aigw-diagnostics'
  scope: apim
  properties: {
    workspaceId: logAnalytics.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        category: 'GatewayLogs'
        enabled: true
      }
      {
        category: 'GatewayLlmLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ---- Outputs ----------------------------------------------------------------
output gatewayUrl string = apim.properties.gatewayUrl
output apimName string = apim.name
output logAnalyticsWorkspace string = logAnalytics.name
#disable-next-line outputs-should-not-contain-secrets // demo subscription key, surfaced for the sample client
output subscriptionKey string = subscription.listSecrets().primaryKey
output chatEndpointExample string = '${apim.properties.gatewayUrl}/openai/deployments/gpt-4o/chat/completions?api-version=${openAiApiVersion}'
