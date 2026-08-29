# GitHub Webhook Auto-Deploy Setup

This webhook lets GitHub notify the local dashboard when `ai-build-stabilization` receives a push. The endpoint validates GitHub's `X-Hub-Signature-256` header before running a local pull in the runtime repo.

## GitHub Webhook Settings

Webhook URL:

```text
https://tasks.callahanautoaz.net/webhooks/github-deploy
```

Content type:

```text
application/json
```

Events to send:

```text
Just the push event
```

Secret:

Use the same value stored locally in the Windows environment variable `GITHUB_WEBHOOK_SECRET`.

## Generate A Secret

Run this in PowerShell to generate a strong random secret:

```powershell
[Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

Copy the generated value into the GitHub webhook secret field.

## Set GITHUB_WEBHOOK_SECRET On Windows

Set the machine-level environment variable from an elevated PowerShell window:

```powershell
[Environment]::SetEnvironmentVariable("GITHUB_WEBHOOK_SECRET", "<paste-generated-secret-here>", "Machine")
```

Then restart the Flask dashboard process so it can read the new environment variable.

To confirm the variable exists without printing the secret:

```powershell
if ([Environment]::GetEnvironmentVariable("GITHUB_WEBHOOK_SECRET", "Machine")) { "GITHUB_WEBHOOK_SECRET is set" } else { "GITHUB_WEBHOOK_SECRET is missing" }
```

## Runtime Behavior

On a valid push to `ai-build-stabilization`, the webhook runs:

```powershell
git -C C:\AI-RUNTIME\shop-observer-core pull origin ai-build-stabilization
```

Deploy results are written to:

```text
logs/deploy.log
```

Invalid signatures return HTTP 403. Pushes to other branches return HTTP 200 with `{"status": "ignored"}`.
