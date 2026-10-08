# One-time setup: let GitHub Actions write to your Drive

This lets the `.github/workflows/ingest.yml` workflow run the ingest on
GitHub's servers and write straight to your Google Drive, so Claude can
trigger it with `gh workflow run` instead of you clicking through Colab.
Your laptop is never involved in the actual ingest.

Authenticates as *you* (OAuth), not a service account: service accounts
have no Drive storage quota of their own, so writes into a folder
merely shared with one fail with `storageQuotaExceeded` unless it's a
Shared Drive, which needs a paid Google Workspace plan.

## 1. Create the Drive folder

In your own Google Drive, create a folder named `pitchgraph` (top-level,
in "My Drive") if it doesn't already exist. Open it and copy its ID from
the URL: `drive.google.com/drive/folders/<THIS_PART_IS_THE_ID>`.

## 2. Authorize rclone as yourself

rclone ships with its own already-verified Google OAuth app, so no GCP
project or credentials need creating.

1. Install rclone (`winget install Rclone.Rclone` on Windows).
2. In a terminal: `rclone authorize "drive"`.
3. It opens your browser — sign in as the account that owns the
   `pitchgraph` folder, approve access.
4. It prints a token blob back in the terminal, e.g.
   `{"access_token":"...","token_type":"Bearer","refresh_token":"...","expiry":"..."}`.
   Keep this private, it's a credential — only the long-lived
   `refresh_token` inside it actually matters; the `access_token` goes
   stale within an hour regardless.

## 3. Add two secrets to the GitHub repo

In github.com/akabra13/football_graph_predictor -> Settings -> Secrets
and variables -> Actions -> New repository secret:

- `GDRIVE_OAUTH_TOKEN` — paste the entire token blob from step 2.4.
- `GDRIVE_FOLDER_ID` — the folder ID from step 1.

## 4. Done

Once both secrets exist, tell Claude -- it can run
`gh workflow run ingest.yml` (optionally with `-f only="43_106"` to test
on one competition-season first) and check progress with
`gh run watch`, without any further action from you.

If the workflow ever starts failing with an auth error, the OAuth token
has likely gone stale (Google access tokens expire; rclone normally
refreshes them automatically using the `refresh_token`, but if that's
ever revoked, re-run step 2 and update the `GDRIVE_OAUTH_TOKEN` secret).
