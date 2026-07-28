# Setup guide

This guide explains how to create a private, automatically updated archive of the traffic data for your public GitHub repositories.

No terminal, local computer, server, or programming knowledge is required.

## What you will get

Once installed, the archive collects and stores:

- Daily repository views
- Daily unique-view counts
- Daily clones
- Daily unique-clone counts
- Top referring sites
- Most-viewed repository paths
- One Markdown dashboard per repository
- One combined dashboard for all repositories
- Long-term CSV history
- Private SVG charts

GitHub normally exposes only the latest 14 days of repository traffic. This project retrieves that window every day and stores each date permanently.

## Before you begin

You need:

- A personal GitHub account
- At least one public repository owned by that account
- Permission to view the repository's traffic page
- Approximately five minutes for the initial setup

## 1. Create your private archive

1. Return to the public template repository.
2. Click **Use this template**.
3. Select **Create a new repository**.
4. Choose your personal GitHub account as the owner.
5. Enter a name such as:

   ```text
   github-traffic-archive
   ```

6. Set the repository visibility to **Private**.
7. Click **Create repository**.

> [!IMPORTANT]
> Keep the generated repository private. It will contain your traffic history, referring sites, and most-viewed repository paths.

The new repository is independent from the public template. Your collected data will not be sent back to the template repository.

## 2. Create a fine-grained token

The collector needs a token because GitHub does not allow the default workflow token to read traffic data from your other repositories.

Open:

```text
GitHub profile picture
→ Settings
→ Developer settings
→ Personal access tokens
→ Fine-grained tokens
→ Generate new token
```

Use these settings:

| Setting | Value |
|---|---|
| Token name | `github-traffic-archive` |
| Description | `Read traffic statistics for my repositories` |
| Resource owner | Your personal GitHub account |
| Expiration | A duration you are comfortable renewing |
| Repository access | **All repositories** |
| Administration | **Read-only** |
| Metadata | **Read-only**, automatically added |

Leave every other permission set to **No access**.

### Why “All repositories”?

It allows newly created public repositories to be discovered automatically.

The collector itself selects only public repositories. It does not collect traffic from private repositories.

For a more restrictive setup, select **Only select repositories** and manually choose the repositories to track. You will then need to update the token whenever you create another repository.

Click **Generate token**, then copy the token immediately.

> [!CAUTION]
> Never place the token in `README.md`, `config.yaml`, a source file, an issue, or a workflow file.

Official GitHub documentation:

- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- https://docs.github.com/en/rest/metrics/traffic

## 3. Store the token as an Actions secret

Open the private archive repository you created.

Go to:

```text
Settings
→ Secrets and variables
→ Actions
→ Secrets
→ New repository secret
```

Create the following secret:

```text
Name: TRAFFIC_TOKEN
Secret: paste the fine-grained token
```

The name must be exactly:

```text
TRAFFIC_TOKEN
```

Click **Add secret**.

GitHub encrypts the value and does not display it again. The workflow only exposes it to the traffic-collection process.

## 4. Run the first collection

Open:

```text
Actions
→ Collect GitHub traffic
```

Click:

```text
Run workflow
→ Run workflow
```

Wait for the run to appear, then open it.

A successful collection displays a summary similar to:

```text
Repositories discovered: 6
Repositories selected:   5
Repositories filtered:   1
Repositories updated:    5
Repositories unchanged:  0
Traffic inaccessible:    0
Partial collections:     0
Failed collections:      0
```

The archive repository itself is automatically filtered.

After the workflow finishes, return to the repository's **Code** page. The root README is now your combined dashboard.

## 5. Automatic daily updates

No additional configuration is required.

The workflow runs every day at:

```text
03:17 UTC
```

It performs the following operations:

1. Discovers public repositories owned by your account.
2. Applies the filters from `config.yaml`.
3. Retrieves the latest 14 days of views and clones.
4. Updates existing dates instead of duplicating them.
5. Saves a dated snapshot of referrers and popular paths.
6. Regenerates the Markdown dashboards and SVG charts.
7. Commits the changed files back to the private archive.

You may also run the workflow manually at any time.

## Repository configuration

The default `config.yaml` is:

```yaml
repositories:
  include_forks: false
  include_archived: false
  exclude: []
```

### Include forks

```yaml
repositories:
  include_forks: true
```

### Include archived repositories

```yaml
repositories:
  include_archived: true
```

### Exclude individual repositories

```yaml
repositories:
  include_forks: false
  include_archived: false

  exclude:
    - old-project
    - test-repository
```

Use repository names only, without your username.

Changes to `config.yaml` take effect during the next workflow run.

## Data structure

The workflow creates:

```text
charts/
├── total-views.svg
├── total-unique-views.svg
├── total-clones.svg
└── total-unique-clones.svg

data/
└── repos/
    └── repository-name/
        ├── README.md
        ├── traffic.csv
        ├── charts/
        ├── referrers/
        └── paths/
```

### `traffic.csv`

This is the permanent daily history:

```csv
date,views,unique_views,clones,unique_clones
2026-07-26,55,49,3,3
2026-07-27,29,20,2,2
```

Each UTC date is stored once. Repeated workflow runs update an existing date rather than appending a duplicate.

### Referrers and paths

GitHub returns only the current top entries for a rolling traffic window. The archive therefore stores them as dated snapshots.

These snapshots must not be added together because consecutive windows overlap.

## Understanding unique counts

GitHub reports unique counts for each repository and each day, but does not provide visitor identities.

For example:

```text
Monday: 10 unique viewers
Tuesday: 8 unique viewers
```

The dashboard can report 18 daily unique-view observations, but it cannot determine whether some people visited on both days.

The same limitation applies across repositories.

For this reason, the dashboard labels these metrics as sums of daily unique counts rather than all-time distinct visitors.

## Privacy and permissions

Two separate tokens are involved:

| Credential | Purpose |
|---|---|
| `TRAFFIC_TOKEN` | Reads traffic statistics from your repositories |
| Workflow `GITHUB_TOKEN` | Commits generated data into the archive |

`TRAFFIC_TOKEN` has read-only Administration permission. It is not used to modify your tracked repositories.

The workflow's temporary `GITHUB_TOKEN` is restricted to writing content in the archive repository.

No data is sent to an external analytics service.

## GitHub Actions usage and cost

The workflow uses a standard Linux GitHub-hosted runner.

A job that lasts approximately 30 seconds is billed as one minute in a private repository because partial job minutes are rounded up.

With one run per day:

| Period | Approximate billed usage |
|---|---:|
| 28-day month | 28 minutes |
| 30-day month | 30 minutes |
| 31-day month | 31 minutes |
| One year | 365 minutes |

GitHub currently includes:

| Plan | Included private-repository minutes |
|---|---:|
| GitHub Free | 2,000 minutes per month |
| GitHub Pro | 3,000 minutes per month |

At 31 minutes per month, this project uses approximately 1.55% of the GitHub Free monthly allowance.

Expected cost while remaining within the included allowance:

```text
0 USD
```

Standard GitHub-hosted runners are free for public repositories. However, making this archive public would expose its collected analytics, so a private archive is strongly recommended.

If the account exceeds its included allowance and has paid usage enabled, the standard two-core Linux runner is currently priced at:

```text
0.006 USD per minute
```

GitHub pricing can change. Consult the current official documentation:

- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/billing/reference/actions-runner-pricing
- https://docs.github.com/en/billing/reference/product-usage-included

## Troubleshooting

### The workflow is skipped

The workflow is intentionally skipped only inside the original public template repository.

Make sure you created a new repository using **Use this template** rather than trying to run the template itself.

### `TRAFFIC_TOKEN environment variable is missing`

The Actions secret was not created or its name is incorrect.

The required name is:

```text
TRAFFIC_TOKEN
```

### All repositories are inaccessible

Check that the fine-grained token has:

```text
Administration: Read-only
```

Also confirm that the token belongs to the same personal account that owns the repositories.

### The workflow cannot push its commit

Open:

```text
Settings
→ Actions
→ General
→ Workflow permissions
```

Select:

```text
Read and write permissions
```

Save the setting, then run the workflow again.

### A repository is missing

Check whether it is:

- Private
- A fork while `include_forks` is disabled
- Archived while `include_archived` is disabled
- Listed under `exclude`
- Missing from the token's selected repository access

### The dashboard did not change after a rerun

That is normal when GitHub returned the same data.

The workflow avoids creating an unnecessary commit when the stored data and generated dashboard are unchanged.

### A scheduled run did not start at exactly 03:17 UTC

Scheduled GitHub Actions workflows may occasionally start later during periods of high demand. The next daily run can still retrieve overlapping traffic data.

Use **Run workflow** for a manual collection when necessary.

## Renewing or replacing the token

Create a replacement fine-grained token with the same permissions.

Then open:

```text
Settings
→ Secrets and variables
→ Actions
```

Update the `TRAFFIC_TOKEN` secret.

No source-code or workflow modification is required.

## Removing the archive

Delete the private archive repository and revoke the fine-grained token from your personal token settings.

Deleting the archive permanently removes the stored CSV, JSON, Markdown, and SVG files.
