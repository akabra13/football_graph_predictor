# One-time setup: let GitHub Actions write to your Drive

This lets the `.github/workflows/ingest.yml` workflow run the ingest on
GitHub's servers and write straight to your Google Drive, so Claude can
trigger it with `gh workflow run` instead of you clicking through Colab.
Your laptop is never involved.

## 1. Create a Google Cloud service account

1. Go to console.cloud.google.com, create a project (or reuse one) — name
   doesn't matter, e.g. "pitchgraph-ci".
2. APIs & Services -> Library -> enable **Google Drive API**.
3. APIs & Services -> Credentials -> Create Credentials -> **Service account**.
   Name it e.g. `pitchgraph-ingest`. No roles needed, no user access needed.
4. Open the new service account -> Keys -> Add key -> Create new key -> JSON.
   This downloads a `.json` file — keep it private, it's a credential.
5. Note the service account's email address (looks like
   `pitchgraph-ingest@your-project.iam.gserviceaccount.com`).

## 2. Create and share a Drive folder

Service accounts don't have a personal "My Drive", so the workflow needs
a folder *you* own, shared with it.

1. In your own Google Drive, create a folder named `pitchgraph` (if it
   doesn't already exist).
2. Right-click it -> Share -> add the service account's email from step
   1.5, give it **Editor** access.
3. Open the folder and copy its ID from the URL:
   `drive.google.com/drive/folders/<THIS_PART_IS_THE_ID>`.

## 3. Add two secrets to the GitHub repo

In github.com/akabra13/football_graph_predictor -> Settings -> Secrets
and variables -> Actions -> New repository secret:

- `GDRIVE_SA_KEY_JSON` — paste the *entire contents* of the JSON key file
  from step 1.4.
- `GDRIVE_FOLDER_ID` — the folder ID from step 2.3.

## 4. Done

Once both secrets exist, tell Claude -- it can run
`gh workflow run ingest.yml` (optionally with `-f only="43_106"` to test
on one competition-season first) and check progress with
`gh run watch`, without any further action from you.
