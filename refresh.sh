#!/bin/bash
# Daily refresh for GitHub 每日热门: fetch trending -> rebuild -> redeploy.
# Run from ~/workspace/money-projects/gh-trending (or anywhere; paths are absolute).
# Exits non-zero on any failure and never deploys a thin/failed list.
set -e
cd ~/workspace/money-projects/gh-trending
VENV=~/workspace/custom-connectors/custom.cloudflare/.venv/bin/python
CF=~/workspace/custom-connectors/custom.cloudflare/bin/cf_pages.py

echo "== 0. snapshot current data into archives/ =="
# Preserve today's already-fetched list before fetch overwrites it, so
# the archive page for that date keeps the list as first fetched.
python3 - <<'EOF'
import json, shutil
from pathlib import Path
p = Path("trending.json")
d = json.loads(p.read_text(encoding="utf-8"))
a = Path("archives") / (d["fetched_date"] + ".json")
a.parent.mkdir(exist_ok=True)
if a.exists():
    print("archive exists, kept", a)
else:
    shutil.copy(p, a)
    print("archived", a)
EOF

echo "== 1. fetch trending =="
python3 fetch_trending.py trending.json

echo "== 2. build + self-check =="
python3 build_site.py

echo "== 3. deploy to Cloudflare Pages =="
"$VENV" "$CF" deploy site gh-trending-cn

echo "== 4. verify live =="
sleep 5
DATE=$(python3 -c "import json; print(json.load(open('trending.json'))['fetched_date'])")
for p in "" "weekly/" "monthly/" "python/" "javascript/" "typescript/" "rust/" "go/" "chinese/" "advertise/" "archive/" "archive/$DATE/" "newsletter/" "newsletter/$DATE/" "feed.xml" "sitemap.xml"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://gh-trending-cn.pages.dev/$p")
  echo "  /$p -> $code"
  [ "$code" = "200" ] || { echo "VERIFY FAILED on /$p"; exit 1; }
done
curl -s "https://gh-trending-cn.pages.dev/sitemap.xml" | grep -q "archive/$DATE/" \
  || { echo "VERIFY FAILED: sitemap missing archive/$DATE/"; exit 1; }
echo "  sitemap contains archive/$DATE/"
curl -s "https://gh-trending-cn.pages.dev/sitemap.xml" | grep -q "newsletter/$DATE/" \
  || { echo "VERIFY FAILED: sitemap missing newsletter/$DATE/"; exit 1; }
echo "  sitemap contains newsletter/$DATE/"
curl -s "https://gh-trending-cn.pages.dev/" | grep -q "promo-card" \
  || { echo "VERIFY FAILED: no in-feed promo card on homepage"; exit 1; }
echo "  homepage contains in-feed promo card"
curl -s "https://gh-trending-cn.pages.dev/" | grep -q "newsletter/$DATE/" \
  || { echo "VERIFY FAILED: no newsletter link on homepage"; exit 1; }
echo "  homepage links to today's newsletter issue"
curl -s "https://gh-trending-cn.pages.dev/" | grep -q "lang-badge" \
  || { echo "VERIFY FAILED: no language badge on homepage"; exit 1; }
curl -s "https://gh-trending-cn.pages.dev/" | grep -q "今日 +" \
  || { echo "VERIFY FAILED: no stars-today on homepage"; exit 1; }
echo "  homepage shows language badges + stars-today (three-piece check)"
echo "refresh done: https://gh-trending-cn.pages.dev/"
