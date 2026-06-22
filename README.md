# Xaylo — EU Grants Monitor

Automated monitoring of EU funding calls from the EC Funding & Tenders Portal.
Every Monday, scans 200+ programmes and sends an email with relevant calls only.

## What it does

- Scans all EC portal programmes (Horizon, EDF, LIFE, EIC, Digital Europe, Erasmus+...)
- Filters only Open + Forthcoming calls
- Searches keywords in the full text of each call
- Sends only new calls — previously sent calls are not repeated
- Filters only calls relevant for SMEs

## Files

| File | Description |
|---|---|
| `index.html` | Landing page + configurator |
| `eu_grants_agent.py` | Main Python script |
| `seen_identifiers.json` | History of sent calls |
| `.github/workflows/eu_grants.yml` | GitHub Actions — runs every Monday |

## Setup

1. Fork this repository
2. Edit `eu_grants_agent.py` — set `EMAIL_PRIJEMCA`
3. Enable GitHub Pages: `Settings → Pages → main → / (root)`
4. Set workflow permissions: `Settings → Actions → General → Read and write permissions`
5. Run first job: `Actions → EU Grants Agent → Run workflow`

## Tech stack

- Python 3.11
- GitHub Actions (scheduler)
- GitHub Pages (frontend)
- Gmail SMTP (email)
- EC Search API (data)

## Data source

[EC Funding & Tenders Portal](https://ec.europa.eu/info/funding-tenders/opportunities/portal)
