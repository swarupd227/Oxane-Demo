# Deploying to Azure

The workbench runs as one always-on container. It serves the app and API on one address, with a recorded run built in, so it needs no model key to work.

## What gets created

| Resource | Purpose | Rough monthly cost |
|---|---|---|
| Container App, 1 vCPU, 2 GiB, one replica | The workbench | US$70 |
| PostgreSQL Flexible Server, B1ms | Session and audit log | US$15 |
| Container Registry, Basic | The image | US$5 |
| Log Analytics | Container logs | Under US$5 |
| Key Vault, managed identity | Secrets | Under US$1 |

These costs are estimates to check against the Azure pricing calculator. Total: about US$95 a month while it exists. Delete the resource group to stop all charges.

## What you need

- An Azure subscription where you can create a resource group and assign roles on it.
- Permission to register an application in Entra ID. If you don't have it, ask an administrator to create one, using the redirect address in the script.
- The sign-in names of the people who will use it: at least one onboarding analyst and one second analyst, who must be different people.
- For live runs only: a Claude deployment on Microsoft Foundry. Replay needs none of this.

## Steps

Run these in PowerShell 7 from the project folder.

1. Install the tools, once.

```powershell
winget install --id Microsoft.AzureCLI --exact
```

2. Sign in, in a new terminal, and pick the subscription.

```powershell
az login
```

```powershell
az account set --subscription "<subscription name or ID>"
```

3. Deploy. This takes about 15 minutes.

```powershell
./infra/deploy.ps1 -ResourceGroup rg-oxane-workbench -Location eastus2 -AnalystUsers "analyst@yourcompany.com" -ApproverUsers "reviewer@yourcompany.com"
```

The script prints a generated database password once. Keep it, and set it as `OXANE_POSTGRES_PASSWORD` before any later deployment, otherwise the app will lose its database connection.

4. Open the address the script prints, and sign in.

## After deploying

Use a person on each list, in two separate browser sessions.

1. Confirm the deal page opens only after sign-in.
2. As the analyst, work the case through to approval, and confirm the Approve button stays disabled.
3. As the second analyst, approve and download the load file.
4. Confirm the audit log shows both real names.

## Live runs

Replay is the normal mode. To prove a live run on Azure, pass `-FoundryResource` and `-FoundryApiKey` to the deploy script, then run this. It costs about US$1.

```powershell
az containerapp exec --resource-group rg-oxane-workbench --name oxaneworkbench --command "python -m app.evaluate --runs 1"
```

Check first that `claude-opus-5-5` is offered in your Foundry region and subscription type.

## Removing it

This deletes everything, including the audit log.

```powershell
az group delete --name rg-oxane-workbench
```

## Known limits

- The database accepts connections from Azure services, protected by its password. A private network would be the step up for a pilot.
- Logs go to Log Analytics. Application Insights is not set up.
- Files are built into the image, so Blob Storage is not used. A pilot that accepts real uploads would need it.
- The Sandbox labels stay on in Azure, because the data is still synthetic.
