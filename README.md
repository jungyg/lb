# Last Bottle catalog

A GitHub Pages site listing every product in Last Bottle's public Shopify feed.
A scheduled GitHub Action fetches the feed every 30 minutes and redeploys the page.

## Setup

1. Create a **public** repository and push these files to `main`.
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Actions tab → **Update catalog** → **Run workflow** (the first run creates the data).
4. The site is at `https://<your-username>.github.io/<repo-name>/`.

## Files

- `scripts/fetch.py`: fetches `lastbottlewines.com/products.json` (all pages) and normalizes it. Standard library only.
- `data/catalog.json`: committed only when something changes, so `git log -p data/catalog.json` is a price and availability history.
- `site/index.html`: the page. It reads `site/products.json`, which is generated on each run and not committed.
- `.github/workflows/update.yml`: schedule, commit, and deploy.

## Local preview

    python scripts/fetch.py
    python -m http.server -d site

Then open http://localhost:8000.
