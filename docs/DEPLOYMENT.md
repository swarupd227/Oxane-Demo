# Deploying to Azure

The workbench runs as one always-on container. It serves both demos, onboarding at `/` and the monitoring cycle at `/monitoring`, and the API on one address. The recorded runs are built in, so it needs no model key to work. The image build regenerates the deal pack and the monitoring cycle and fails if either differs from `deal-kit/pack.manifest.json` or `deal-kit/cycle.manifest.json`.

## What gets created

| Resource | Purpose | Rough monthly cost |
|---|---|---|
| Container App, 1 vCPU, 2 GiB, one replica | The workbench | US$70 |
| PostgreSQL Flexible Server, B1ms | Session and audit log | US$15 |
| Container Registry, Basic | The image | US$5 |
| Log Analytics | Container logs | Under US$5 |
| Key Vault, managed identity | Secrets (the identity reads them through an access policy) | Under US$1 |

These costs are estimates to check against the Azure pricing calculator. Total: about US$95 a month while it exists. Delete the resource group to stop all charges.

## What you need

- An Azure subscription where you can create a resource group. Contributor is enough: the template assigns no roles.
- Permission to register an application in Entra ID. If you don't have it, ask an administrator to create one, using the redirect address in the script.
- The sign-in names of the people who will use it: at least one analyst and one second analyst, who must be different people. A person is on one list only; someone on both counts as a second analyst. You can deploy with only an analyst and add the second analyst later: everything except approval then works.
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
./infra/deploy.ps1 -Subscription "<subscription name or ID>" -ResourceGroup rg-oxane-workbench -Location eastus2 -AnalystUsers "analyst@yourcompany.com" -ApproverUsers "reviewer@yourcompany.com"
```

On the first deployment the script generates a database password and saves it to `.env.azure` in the project folder, which git ignores. Later deployments read it from there, or from `OXANE_POSTGRES_PASSWORD` if set. Keep it: a deployment with a different password leaves the app without its database.

If the subscription does not allow ACR Tasks (`az acr build`), add `-LocalBuild` to build with local Docker and push. If the region does not offer PostgreSQL's Burstable B1ms to the subscription (`SkuNotAvailable`), add `-PostgresLocation centralus` or another nearby region.

If you may not register applications in Entra ID, the script stops at "Registering sign-in with Entra" after printing the sign-in redirect address, and leaves the app undeployed rather than open. Ask an administrator to register a single-tenant web application ("Accounts in this organizational directory only") with that redirect address and ID tokens enabled, and to give you its client ID and a client secret. Then run the same command with `-AuthClientId "<client ID>"`, and the secret in `OXANE_AUTH_CLIENT_SECRET` or `-AuthClientSecret`.

4. Open the address the script prints, and sign in.

## After deploying

Use a person on each list, in two separate browser sessions.

1. Confirm the deal page opens only after sign-in.
2. As the analyst, work the case through to approval, and confirm the Approve button stays disabled.
3. As the second analyst, approve and download the load file.
4. Confirm the audit log shows both real names.
5. Open `/monitoring` and do the same for the May cycle: the analyst triages, the second analyst approves the lender packs.

### Smoke test

In demo mode (`-NoSignIn`), add `-SmokeTest` to run the browser suite against the new app once it is deployed. The script waits for `/api/health`, then runs the Playwright `azure` project from `tests/e2e` (it installs the packages and Chromium if they are missing, so Node.js is needed). The access code comes from `DEMO_ACCESS_CODE`, or `OXANE_DEMO_ACCESS_CODE` in `.env.azure`; without one, the tests that need it skip. A failing test fails the script.

```powershell
./infra/deploy.ps1 -Subscription "<subscription name or ID>" -ResourceGroup rg-oxane-workbench -Location eastus2 -PostgresLocation centralus -NoSignIn -SmokeTest
```

To run it on its own against the deployed app, see "Smoke-test the hosted app" in the README. The `azure` project skips the specs that reset the shared scripted case or need the test model (`fallback`, `screens`, `flow`, `drills`, and deals test (d)); `context.spec.ts`, `settings.spec.ts` and deals test (c) run. Test (c) leaves a new client and live facility behind, and the context checks archive their throwaway client and case. With sign-in on, the smoke test is skipped, since it acts as each persona.

To add or change who can use it, redeploy with new `-AnalystUsers`, `-ApproverUsers` and `-SeniorUsers` (heads of monitoring, the third approval level some clients need), or change the `ANALYST_USERS`, `APPROVER_USERS` and `SENIOR_USERS` settings on the container app. Anyone in the organisation can sign in, but only people on a list can act.

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
- The app pulls its image with the registry's admin credential, so a Contributor can deploy without assigning roles. With Owner or User Access Administrator, an AcrPull role for the managed identity would be the step up.
- Logs go to Log Analytics. Application Insights is not set up.
- Files are built into the image, so Blob Storage is not used. A pilot that accepts real uploads would need it.
- The Sandbox labels stay on in Azure, because the data is still synthetic.
