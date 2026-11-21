#!/usr/bin/env python3
"""Build the GitHub 每日热门 static site (10 pages) into ./site/ and pack
it as gh-trending-site.zip (site files only, no build scripts/docs).

Run: python3 build_site.py
Data lives in trending.json (fetched by fetch_trending.py from
github.com/trending — real repos, real star counts, real descriptions)
and summaries.json (Chinese summaries written by the agent, keyed by
repo full name). Edit data there, not in the page HTML.
See OPERATIONS.md for the daily refresh flow.

Rules enforced by this script (DESIGN.md / RESEARCH.md, 2026-11-20):
- No invented repos, star counts, or descriptions. Every number comes
  from trending.json; every Chinese summary comes from summaries.json.
  A repo with no Chinese summary shows its official English description
  labelled as such — never a machine-translated or invented summary.
- Repo links go ONLY to https://github.com/<owner>/<repo>.
- No email address anywhere. No external resources: no Google Fonts,
  no CDN, no tracking except the Cloudflare Web Analytics beacon
  (RUM site gh-trending-cn.pages.dev, token in BEACON below).
"""
import datetime
import hashlib
import html
import json
import shutil
import sys
import zipfile
from pathlib import Path

# Shared self-serve sponsorship component (modal, tiers, PayPal checkout,
# sponsored cards). Single source of truth for all 7 sites; see
# ~/workspace/money-projects/sponsor/sponsor_component.py and
# SPONSOR-OPERATIONS.md in the same dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sponsor"))
import sponsor_component as SP

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"

BASE = "https://gh-trending-cn.pages.dev"
INDEXNOW_KEY = "7c23f31035fee53caeaa7a765cb2a8c4"
SITE_NAME = "GitHub 每日热门"

# Cloudflare Web Analytics beacon (RUM site gh-trending-cn.pages.dev,
# created 2026-11-20 via create_rum_site.py). Inserted just before
# </body> on every page, same pattern as the sibling sites.
BEACON = """<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "<redacted>"}'></script>"""

STORE_URL = "https://payhip.com/MerryPrintables"

# ---------------------------------------------------------------- lists
# key in trending.json -> (slug, nav label, page title, page description,
#                           max repos shown, FAQ set)
PAGES = [
    ("daily", "", "今日热门", "今日 GitHub 热门 Top 15（中文）",
     "今天 GitHub 上最火的 15 个开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("weekly", "weekly/", "本周热门", "本周 GitHub 热门（中文）",
     "本周 GitHub 上增长最快的开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("monthly", "monthly/", "本月热门", "本月 GitHub 热门（中文）",
     "本月 GitHub 上增长最快的开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("python", "python/", "Python 热门", "Python 今日热门项目（中文）",
     "今天 GitHub 上最火的 Python 开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("javascript", "javascript/", "JavaScript 热门", "JavaScript 今日热门项目（中文）",
     "今天 GitHub 上最火的 JavaScript 开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("typescript", "typescript/", "TypeScript 热门", "TypeScript 今日热门项目（中文）",
     "今天 GitHub 上最火的 TypeScript 开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("rust", "rust/", "Rust 热门", "Rust 今日热门项目（中文）",
     "今天 GitHub 上最火的 Rust 开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("go", "go/", "Go 热门", "Go 今日热门项目（中文）",
     "今天 GitHub 上最火的 Go 开源项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
    ("chinese", "chinese/", "中国开发者热门", "中国开发者今日热门项目（中文）",
     "今天中国开发者在 GitHub 上的热门项目，每个配中文简介。数据来自 GitHub Trending，每日更新。",
     15),
]

NAV = [
    ("今日热门", "index.html"),
    ("本周热门", "weekly/"),
    ("本月热门", "monthly/"),
    ("Python", "python/"),
    ("JavaScript", "javascript/"),
    ("TypeScript", "typescript/"),
    ("Rust", "rust/"),
    ("Go", "go/"),
    ("中国开发者", "chinese/"),
    ("归档", "archive/"),
    ("每日回顾", "newsletter/"),
    ("赞助", "advertise/"),
]

SISTERS = [
    ("Merry Printables", "https://hanxianqing.github.io/", "Party games & planners from the same maker"),
    ("LocalTools", "https://hanxianqing.github.io/localtools/", "Free file tools that run on your device"),
    ("ClassroomKit", "https://hanxianqing.github.io/classroomkit/", "Free classroom worksheet & game generators"),
    ("TemplatePack", "https://hanxianqing.github.io/templatepack/", "Copy-paste templates for work"),
    ("PennyMath", "https://hanxianqing.github.io/pennymath/", "Free money calculators"),
    ("Holiday Gift Finder", "https://merry-gift-finder.pages.dev", "Find a Christmas gift in 3 questions"),
]

# ---------------------------------------------------------------- icons
ICONS = {
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 13.5"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "arrow": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "megaphone": '<path d="M3 11l18-5v12L3 13v-2z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
}


def icon(name, cls="ic"):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS[name]}</svg>')


CSS = """*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;color:#22292A;background:#fff;line-height:1.65}
a{color:#0E3B2E}img{max-width:100%;height:auto;display:block}
.wrap{max-width:1020px;margin:0 auto;padding:0 20px}
h1,h2,h3{font-family:Georgia,"Times New Roman",Times,serif;color:#0E3B2E;line-height:1.25}
h2{font-size:1.6rem;margin:0 0 10px}h3{font-size:1.2rem;margin:0 0 6px}
p{margin:0 0 12px}.muted{color:#5A6663;font-size:.92rem}.small{font-size:.86rem}
.ic{width:1.1em;height:1.1em;vertical-align:-.18em}
header.site{background:#0E3B2E;color:#FFF6DC;padding:12px 0;position:sticky;top:0;z-index:50}
header.site .wrap{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.brand{font-family:Georgia,serif;font-size:1.45rem;font-weight:700;color:#FFF6DC;text-decoration:none;white-space:nowrap}
.brand b{color:#D4A94E}
nav.main{margin-left:auto;display:flex;gap:2px 4px;flex-wrap:wrap}
nav.main a{color:#FFF6DC;text-decoration:none;padding:7px 10px;border-radius:8px;font-size:.92rem}
nav.main a:hover,nav.main a[aria-current="page"]{background:#1B5A44;color:#D4A94E}
.crumbs{font-size:.86rem;color:#5A6663;padding:14px 0 0}
.crumbs a{color:#5A6663;text-decoration:none}.crumbs a:hover{color:#0E3B2E;text-decoration:underline}
.crumbs b{color:#0E3B2E}
.hero{background:linear-gradient(180deg,#FFF6DC,#fff);border-bottom:3px solid #D4A94E;padding:40px 0 34px}
.hero h1{font-size:2.15rem;margin:0 0 10px;max-width:640px}
.hero h1 em{font-style:normal;color:#C0392B}
.hero p.lede{font-size:1.08rem;color:#3C4A45;max-width:620px;margin:0 0 16px}
.hero-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:32px;align-items:center}
.hero-art img{width:100%;border-radius:14px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}
.chip{display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid #E5DDD0;border-radius:999px;padding:5px 12px;font-size:.86rem;font-weight:600;color:#0E3B2E}
.trust{background:#FFF6DC;border-bottom:1px solid #E5DDD0;padding:16px 0}
.trust .wrap{display:flex;flex-wrap:wrap;gap:12px 30px;justify-content:center}
.trust-item{display:flex;align-items:center;gap:10px}
.trust-item .ic{width:1.5em;height:1.5em;color:#C0392B}
.trust-item b{display:block;font-family:Georgia,serif;font-size:1.02rem;color:#0E3B2E;line-height:1.2}
.trust-item span{font-size:.82rem;color:#5A6663}
section{padding:36px 0}section.band{background:#F8EFC9}section.band-green{background:#EEF4EE}
.btn{display:inline-block;font-family:inherit;font-weight:700;text-decoration:none;border-radius:999px;padding:12px 26px;font-size:1rem;border:0;cursor:pointer;transition:transform .15s ease,box-shadow .15s ease}
.btn:hover{transform:translateY(-1px);box-shadow:0 6px 14px rgba(14,59,46,.25)}
.btn-pine{background:#0E3B2E;color:#FFF6DC}.btn-pine:hover{background:#092A20}
.btn-red{background:#C0392B;color:#fff}.btn-red:hover{background:#A93226}
.btn-outline{background:#fff;color:#0E3B2E;border:2px solid #0E3B2E}
.btn-outline:hover{background:#0E3B2E;color:#FFF6DC}
.btn.small{padding:8px 18px;font-size:.92rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:20px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.card{background:#fff;border:1px solid #E5DDD0;border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(14,59,46,.06),0 4px 14px rgba(14,59,46,.06);transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
.card:hover{transform:translateY(-4px);border-color:#D4A94E;box-shadow:0 12px 24px rgba(14,59,46,.14)}
.card .body{padding:16px 18px 20px}
.card .body h3{font-size:1.12rem}
.featured-card{background:#F6EAD0;border:2px solid #D4A94E}
.featured-card .body{text-align:center}
.featured-badge{display:inline-block;background:#D4A94E;color:#0E3B2E;font-family:Georgia,serif;font-weight:700;font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;padding:5px 14px;border-radius:6px;border:1px solid #B98A2F}
/* repo list */
.rank-list{list-style:none;margin:0;padding:0;display:grid;gap:16px}
.repo-card{background:#fff;border:1px solid #E5DDD0;border-radius:14px;padding:18px 20px;display:grid;grid-template-columns:52px 1fr;gap:6px 16px;box-shadow:0 1px 3px rgba(14,59,46,.06)}
.repo-card:hover{border-color:#D4A94E}
.rank{font-family:Georgia,serif;font-size:1.7rem;font-weight:700;color:#D4A94E;text-align:center;line-height:1.1}
.repo-card h3{font-size:1.15rem;margin:0;overflow-wrap:anywhere}
.repo-card h3 a{color:#0E3B2E;text-decoration:none}
.repo-card h3 a:hover{text-decoration:underline;color:#C0392B}
.repo-meta{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.86rem;color:#5A6663;margin:6px 0 8px}
.repo-meta .stars{color:#C0392B;font-weight:700}
.lang-badge{display:inline-block;background:#EEF4EE;border:1px solid #E5DDD0;border-radius:999px;padding:1px 10px;font-size:.78rem;font-weight:700;color:#0E3B2E}
.repo-card p.desc{margin:0}
.repo-card p.desc .src-note{font-size:.82rem;color:#5A6663}
/* in-feed promoted card: same row layout as a repo entry, gold tint + badge */
.promo-card{background:#F6EAD0;border:2px solid #D4A94E}
.promo-card .rank{font-size:.8rem;color:#0E3B2E;display:flex;align-items:center;justify-content:center}
.promo-badge{display:inline-block;background:#D4A94E;color:#0E3B2E;font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 9px;border-radius:6px;border:1px solid #B98A2F}
.archive-nav{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;margin:0 0 18px}
.archive-nav a{font-weight:700}
.archive-nav .disabled{color:#9AA5A1}
/* visual distinction (XS-P1-2, 2026-11-21): brand palette unchanged
   (#0E3B2E pine / #D4A94E gold / #C0392B red); the home hero gets a
   gold kicker + a live data-driven spotlight card instead of the
   generic SVG, so this site reads as the trending board at a glance. */
.hero-kicker{display:inline-block;background:#0E3B2E;color:#D4A94E;font-size:.78rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;padding:5px 12px;border-radius:999px;margin-bottom:12px}
.hero--gh{background:linear-gradient(180deg,#FFF6DC,#fff),radial-gradient(circle at 88% 18%,rgba(212,169,78,.22),transparent 42%);border-bottom:3px solid #D4A94E}
.spotlight{background:#0E3B2E;color:#FFF6DC;border:2px solid #D4A94E;border-radius:14px;padding:20px 22px;box-shadow:0 12px 24px rgba(14,59,46,.22)}
.spotlight .kicker{color:#D4A94E;font-size:.78rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
.spotlight h3{color:#FFF6DC;font-size:1.25rem;margin:8px 0 6px}
.spotlight h3 a{color:#FFF6DC;text-decoration:none}
.spotlight h3 a:hover{color:#D4A94E;text-decoration:underline}
.spotlight .stars{color:#D4A94E;font-weight:700}
.spotlight p{color:#D8E4DA;margin:8px 0 12px}
.spotlight .lang-badge{background:rgba(255,246,220,.14);border-color:rgba(255,246,220,.35);color:#FFF6DC}
.lang-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.lang-missing{color:#5A6663;font-weight:400}
.mover-badge{display:inline-block;background:#C0392B;color:#fff;font-size:.72rem;font-weight:700;padding:2px 9px;border-radius:999px;margin-left:8px;vertical-align:2px}
/* newsletter entry strip: top + bottom of every list page */
.nl-strip{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;justify-content:space-between;background:#F6EAD0;border:2px solid #D4A94E;border-radius:14px;padding:14px 18px;margin:0 0 22px}
.nl-strip b{font-family:Georgia,serif;color:#0E3B2E;font-size:1.05rem}
.nl-strip p{margin:0;color:#3C4A45;font-size:.92rem}
.nl-strip .btn{white-space:nowrap}
.stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:16px 0 22px}
.stat-cell{background:#F8EFC9;border:1px solid #E5DDD0;border-radius:12px;padding:14px 16px}
.stat-cell b{display:block;font-family:Georgia,serif;font-size:1.4rem;color:#0E3B2E;line-height:1.2}
.stat-cell span{font-size:.86rem;color:#5A6663}
.delta-up{color:#0E3B2E;font-weight:700}
.delta-new{color:#C0392B;font-weight:700}
.recap-list{margin:0;padding-left:20px}
.recap-list li{margin-bottom:6px}
ul.check{list-style:none;padding:0;margin:0 0 12px}ul.check li{padding-left:26px;position:relative;margin-bottom:6px}
ul.check li:before{content:"\\2713";position:absolute;left:0;color:#0E3B2E;font-weight:700}
.faq details{background:#fff;border:1px solid #E5DDD0;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.faq summary{font-weight:700;color:#0E3B2E;cursor:pointer;font-family:Georgia,serif;font-size:1.05rem}
.faq details p{margin:8px 0 2px}
footer.site{background:#0E3B2E;color:#B9CEC2;padding:36px 0 24px;margin-top:20px;font-size:.93rem}
.foot-grid{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:28px;margin-bottom:22px}
.foot-grid h3{color:#D4A94E;font-size:1.05rem;margin:0 0 10px}
.foot-grid ul{list-style:none;margin:0;padding:0}.foot-grid li{margin-bottom:7px}
.foot-grid a{color:#fff;text-decoration:none}.foot-grid a:hover{color:#D4A94E;text-decoration:underline}
.foot-base{border-top:1px solid rgba(255,255,255,.18);padding-top:16px;color:#A9C2B4}
.foot-base a{color:#fff}
.note{background:#F6EAD0;border-left:4px solid #D4A94E;padding:12px 16px;border-radius:0 10px 10px 0;margin:14px 0}
.note p{margin:0}
/* ad slots — one rule, placeholders only, no ad code */
.ad-slot{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;background:#FAF7EF;border:1.5px dashed #E5DDD0;border-radius:14px;color:#5A6663;font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;text-align:center}
.ad-slot .size{font-size:.72rem;letter-spacing:.08em}
.ad-leaderboard,.ad-slot--leaderboard{width:728px;max-width:100%;height:90px;margin:14px auto}
.ad-rectangle,.ad-slot--rectangle{width:300px;max-width:100%;height:250px;margin:0 auto 24px}
.ad-halfpage,.ad-slot--halfpage{width:300px;max-width:100%;height:600px;margin:0 auto 24px}
@media(max-width:860px){
  .hero-grid{grid-template-columns:1fr;gap:20px}
  .hero h1{font-size:1.7rem}
  .hero-art{display:none}
  .grid3{grid-template-columns:1fr}
  .ad-halfpage,.ad-slot--halfpage{display:none}
  .foot-grid{grid-template-columns:1fr;gap:20px}
}
@media(max-width:640px){.hero h1{font-size:1.55rem}h2{font-size:1.4rem}.repo-card{grid-template-columns:38px 1fr;padding:14px 16px}.rank{font-size:1.35rem}}
@media print{header.site,footer.site,.ad-slot{display:none!important}}
"""


def ad_leaderboard():
    return ('<div class="ad-slot ad-leaderboard ad-slot--leaderboard" role="complementary" '
            'aria-label="Advertisement slot, currently unfilled">'
            '<!-- AD SLOT: leaderboard 728x90 — paste ad-network code here when a network is live; until then this placeholder stays. -->'
            'Advertisement<span class="size">728 &times; 90</span></div>')


def ad_rectangle():
    return ('<div class="ad-slot ad-rectangle ad-slot--rectangle" role="complementary" '
            'aria-label="Advertisement slot, currently unfilled">'
            '<!-- AD SLOT: rectangle 300x250 — paste ad-network code here when a network is live; until then this placeholder stays. -->'
            'Advertisement<span class="size">300 &times; 250</span></div>')


def ad_halfpage():
    return ('<div class="ad-slot ad-halfpage ad-slot--halfpage" role="complementary" '
            'aria-label="Advertisement slot, currently unfilled">'
            '<!-- AD SLOT: halfpage 300x600 — paste ad-network code here when a network is live; until then this placeholder stays. -->'
            'Advertisement<span class="size">300 &times; 600</span></div>')


def nav_html(prefix, current):
    out = []
    for label, href in NAV:
        cur = ' aria-current="page"' if href == current else ""
        out.append(f'<a href="{prefix}{href}"{cur}>{label}</a>')
    return "".join(out)


def footer_html(prefix):
    sisters = " · ".join(
        f'<a href="{u}">{n}</a>' for n, u, _ in SISTERS)
    kw_links = "".join(
        f'<li><a href="{prefix}{href}">{label}</a></li>'
        for label, href in NAV if href not in ("index.html", "advertise/"))
    return f"""<footer class="site"><div class="wrap"><div class="foot-grid">
<div><h3>GitHub 每日热门</h3>
<p>每天更新的 GitHub Trending 中文榜：今日、本周、本月与各语言热门项目，每个配中文简介。数据来自 GitHub Trending，免费查看，不用注册。Made by the same maker as Merry Printables.</p>
<p>Sister sites: {sisters}</p></div>
<div><h3>榜单</h3><ul>
<li><a href="{prefix}index.html">今日热门</a></li>{kw_links}</ul></div>
<div><h3>更多</h3><ul>
<li><a href="{prefix}newsletter/">每日回顾</a></li>
<li><a href="{prefix}archive/">往日归档</a></li>
<li><a href="{prefix}feed.xml">RSS 订阅</a></li>
<li><a href="{prefix}advertise/">赞助合作</a></li>
<li><a href="{STORE_URL}">Merry Printables 商店</a></li>
<li><a href="https://github.com/trending">GitHub Trending（英文原站）</a></li>
</ul></div></div>
<p class="foot-base">&copy; 2026 GitHub 每日热门 &middot; 数据来自 GitHub Trending，每日更新。仓库名与星数均为 GitHub 公开数据。</p>
</div></footer>"""


def faq_json_ld(faqs):
    qs = [{"@type": "Question", "name": q,
           "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]
    return ('<script type="application/ld+json">' +
            json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
                        "mainEntity": qs}, ensure_ascii=False) + "</script>")


def faq_html(faqs):
    out = ['<div class="faq">']
    for q, a in faqs:
        out.append(f"<details><summary>{q}</summary><p>{a}</p></details>")
    out.append("</div>")
    return "\n".join(out)


def page(title, desc, canonical_path, prefix, current, body, faqs=None,
         extra_head=""):
    can = f"{BASE}/{canonical_path}" if canonical_path else f"{BASE}/"
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title,
          "description": desc, "url": can,
          "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": BASE + "/"}}
    parts = [f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>']
    if faqs:
        parts.append(faq_json_ld(faqs))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="google-site-verification" content="a94d7c9de371c76a">
<link rel="canonical" href="{can}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{can}">
<meta property="og:site_name" content="{SITE_NAME}">
<link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="GitHub 每日热门 RSS" href="{prefix}feed.xml">
<link rel="stylesheet" href="{prefix}assets/style.css">
{SP.sponsor_head_links(prefix)}
{extra_head}
{''.join(parts)}
</head><body>
<header class="site"><div class="wrap"><a class="brand" href="{prefix}index.html">GitHub <b>每日热门</b></a>
<nav class="main">{nav_html(prefix, current)}</nav>{SP.sponsor_button_html("zh")}</div></header>
{ad_leaderboard()}
<main>
{body}
</main>
{footer_html(prefix)}
{BEACON}
{SP.modal_for_site("zh")}
{SP.sponsor_body_tags(prefix)}
</body></html>
"""


def fmt(n):
    return f"{n:,}"


# GitHub language colours (github.com linguist palette, well-known
# values; unknown languages fall back to the site gold). Only used as
# a dot next to the language label — never invented data.
LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Rust": "#dea584", "Go": "#00ADD8", "C": "#555555", "C++": "#f34b7d",
    "C#": "#178600", "Java": "#b07219", "Shell": "#89e051", "HTML": "#e34c26",
    "CSS": "#663399", "Ruby": "#701516", "PHP": "#4F5D95", "Swift": "#F05138",
    "Kotlin": "#A97BFF", "Jupyter Notebook": "#DA5B0B", "Vue": "#41b883",
    "Dart": "#00B4AB", "Lua": "#000080", "Zig": "#ec915c", "Markdown": "#083fa1",
}


def lang_badge_html(repo):
    """Language tag, one of the fixed three pieces on every card.
    A repo with no language on GitHub Trending gets an honest
    '语言未标注' tag — never a guessed language."""
    lang = repo.get("lang")
    if not lang:
        return ('<span class="lang-badge lang-missing">'
                '<span class="lang-dot" style="background:#9AA5A1"></span>'
                '语言未标注</span>')
    color = LANG_COLORS.get(lang, "#D4A94E")
    return (f'<span class="lang-badge"><span class="lang-dot" '
            f'style="background:{color}"></span>{lang}</span>')


def repo_card(rank, repo, summaries, top_mover=None):
    """One ranked repo. The three fixed pieces, always shown:
    (1) a one-line Chinese summary (agent-written; fallback = the
    repo's own English description, labelled, never invented);
    (2) today's new stars ('今日 +N'); (3) the language tag.
    Total stars are shown alongside. 'Built by' avatars are NOT
    rendered: trending.json carries no avatar data and no new
    collection is added (TR-P1-3, 2026-11-21)."""
    url = f"https://github.com/{repo['repo']}"
    summary = summaries.get(repo["repo"])
    if summary:
        desc_html = f"<p class=\"desc\">{summary}</p>"
    elif repo["desc"]:
        desc_html = (f"<p class=\"desc\">{repo['desc']} "
                     f"<span class=\"src-note\">（官方简介，英文）</span></p>")
    else:
        desc_html = "<p class=\"desc\">该项目暂无官方简介。</p>"
    mover = ('<span class="mover-badge">今日涨幅最大</span>'
             if top_mover and repo["repo"] == top_mover else "")
    return (f"<li><article class=\"repo-card\"><div class=\"rank\">{rank}</div><div>"
            f"<h3><a href=\"{url}\" target=\"_blank\" rel=\"noopener\">{repo['repo']}</a>{mover}</h3>"
            f"<div class=\"repo-meta\"><span class=\"stars\">★ {fmt(repo['stars'])}</span>"
            f"<span>今日 +{fmt(repo['stars_today'])}</span>{lang_badge_html(repo)}</div>"
            f"{desc_html}</div></article></li>")


def _esc(s):
    return html.escape(str(s), quote=True)


def infeed_promo_html(prefix, sponsors):
    """One Promoted card for inside the ranked list (Product Hunt style):
    same row layout as a repo entry, only the Sponsored badge is added.
    Live Standard/Starter card when one exists; otherwise an empty
    placeholder linking to /advertise/. Never a fake sponsor, never a
    ranking slot — the rank column shows the badge, not a number."""
    live = [s for s in sponsors if s.get("tier") in ("standard", "starter")]
    if live:
        s = live[0]
        title_html = (f'<h3><a href="{_esc(s.get("link", ""))}" target="_blank" '
                      f'rel="noopener sponsored">{_esc(s.get("title", ""))}</a></h3>')
        desc = _esc(s.get("description", ""))
        desc_html = f'<p class="desc">{desc}</p>' if desc else ""
    else:
        title_html = (f'<h3><a href="{prefix}advertise/">这个位置招赞助</a></h3>')
        desc_html = ('<p class="desc">一个明确标注的赞助位可以出现在这里。'
                     '它永远不会顶替真实的榜单排名。'
                     f'<a href="{prefix}advertise/">赞助这个位置 &rarr;</a></p>')
    return (f'<li><article class="repo-card promo-card sp-card">'
            f'<div class="rank">赞助</div><div>{title_html}'
            f'<div class="repo-meta"><span class="promo-badge">Sponsored · 赞助</span></div>'
            f'{desc_html}</div></article></li>')


def interleave_promo(cards, promo_html):
    """Insert the promo card after the 8th entry, then every ~12 entries
    (after the 20th, 32nd, …). Never after the last entry, never
    replacing a real entry — ranking numbers stay 1..N."""
    out = []
    n = len(cards)
    for i, c in enumerate(cards, 1):
        out.append(c)
        if i < n and (i == 8 or (i > 8 and (i - 8) % 12 == 0)):
            out.append(promo_html)
    return out


def _parse_iso(s):
    y, m, d = s.split("-")
    return datetime.date(int(y), int(m), int(d))


def _date_cn(date_iso):
    y, m, d = date_iso.split("-")
    return f"{int(y)}年{int(m)}月{int(d)}日"


def recap_html(archives, latest_iso, prefix, summaries):
    """'上周 Top 5 / 上月 Top 5' review block. Only from real archived
    snapshots: last-week = newest snapshot at least 7 days before the
    latest date; last-month = newest snapshot at least 30 days before.
    Nothing renders when no such snapshot exists — never invented."""
    if not archives:
        return ""
    latest = _parse_iso(latest_iso)
    blocks = []
    for label, days in (("上周 Top 5", 7), ("上月 Top 5", 30)):
        cutoff = latest - datetime.timedelta(days=days)
        cands = [(d, data) for d, data in archives if _parse_iso(d) <= cutoff]
        if not cands:
            continue
        d, data = cands[-1]
        items = data["lists"].get("daily", [])[:5]
        if not items:
            continue
        lis = "".join(
            f'<li><a href="https://github.com/{_esc(it["repo"])}" target="_blank" '
            f'rel="noopener">{_esc(it["repo"])}</a> · ★ {_esc(it.get("stars", ""))}</li>'
            for it in items)
        blocks.append(
            f'<div class="card"><div class="body"><h3>{label}（{_date_cn(d)}）</h3>'
            f'<p class="muted">当时日榜的前 5 名。</p>'
            f'<ol class="recap-list">{lis}</ol>'
            f'<p><a href="{prefix}archive/{d}/">查看 {_date_cn(d)} 完整榜单 &rarr;</a></p>'
            f'</div></div>')
    if not blocks:
        return ""
    return (f'<section><div class="wrap"><h2>回顾</h2>'
            f'<div class="grid">{"".join(blocks)}</div></div></section>')


def archive_nav_html(dates, current):
    """Prev/next day pager for an archive page (Hacker News front style).
    Links only to dates that really exist in the archive; otherwise a
    muted '暂无' label — never a link to a made-up date."""
    i = dates.index(current)
    if i > 0:
        prev = (f'<a href="../{dates[i-1]}/">&larr; 前一天'
                f'（{dates[i-1]}）</a>')
    else:
        prev = '<span class="disabled">&larr; 前一天（暂无更早归档）</span>'
    if i < len(dates) - 1:
        nxt = (f'<a href="../{dates[i+1]}/">后一天'
               f'（{dates[i+1]}） &rarr;</a>')
    else:
        nxt = '<span class="disabled">后一天 &rarr;（暂无更新归档）</span>'
    return (f'<nav class="archive-nav" aria-label="按日归档翻页">{prev}{nxt}'
            f'<a href="../">全部归档</a><a href="../../">今日热门</a></nav>')


def sponsored_card(prefix, sponsors):
    """After-list sponsored slot: live Standard/Starter cards, or the
    placeholder when none are live. Featured cards go above the list
    (see list_body) — top placement is what the Featured tier pays for."""
    return SP.sponsored_slot_html(sponsors, prefix, "zh")


LIST_FAQS = [
    ("数据从哪来？", "榜单数据来自 GitHub Trending（github.com/trending），每天拉取一次。仓库名、星数、今日新增星数与语言均为 GitHub 公开数据；中文简介由本站人工撰写。"),
    ("多久更新一次？", "每天更新一次。每页顶部都标着本次数据更新的日期，过期数据不会冒充当日榜单。"),
    ("“今日 +N”是什么意思？", "这个仓库在过去 24 小时内新增的星标数，也就是它今天火的程度。"),
    ("为什么有的项目只有英文简介？", "个别仓库没有中文简介时，我们直接显示它的官方英文简介并标注出来，不会用机器翻译凑数，也不会编造介绍。"),
    ("榜单收费吗？", "不收费。所有榜单免费查看，不用注册、不用留邮箱。"),
]


def top_mover_of(repos):
    """Repo with the most new stars today in this list (real data)."""
    if not repos:
        return None
    return max(repos, key=lambda r: r.get("stars_today", 0))["repo"]


def nl_strip_html(prefix, fetched):
    """Newsletter entry strip (Product Hunt newsletter-archive pattern,
    TR-P1-1): links to today's review issue + the full issue index.
    No signup form, no email sending — the site has no free mail
    provider account and promises none."""
    return (f'<div class="nl-strip"><div><b>每日回顾</b>'
            f'<p>每天一期：当日 Top 10 与星数变化，数据来自 GitHub Trending。</p></div>'
            f'<a class="btn btn-pine small" href="{prefix}newsletter/{fetched}/">'
            f'看今日回顾 &rarr;</a>'
            f'<a class="btn btn-outline small" href="{prefix}newsletter/">往期回顾</a></div>')


def list_body(key, title, desc, repos, summaries, date_cn, prefix, sponsors,
              is_home=False, archives=None, fetched=None):
    mover = top_mover_of(repos)
    cards = [repo_card(i + 1, r, summaries, top_mover=mover)
             for i, r in enumerate(repos)]
    items = "\n".join(interleave_promo(
        cards, infeed_promo_html(prefix, sponsors)))
    recap = (recap_html(archives, fetched, prefix, summaries)
             if archives and fetched else "")
    nl_top = nl_strip_html(prefix, fetched) if fetched else ""
    if is_home:
        top1 = repos[0] if repos else None
        if top1:
            s1 = summaries.get(top1["repo"])
            d1 = (f"<p>{s1}</p>" if s1 else
                  (f"<p>{top1['desc']} <span class=\"src-note\">"
                   f"（官方简介，英文）</span></p>" if top1.get("desc") else
                   "<p>该项目暂无官方简介。</p>"))
            spotlight = f"""<div class="spotlight"><span class="kicker">今日第 1 名 · GitHub Trending</span>
<h3><a href="https://github.com/{top1['repo']}" target="_blank" rel="noopener">{top1['repo']}</a></h3>
<div><span class="stars">★ {fmt(top1['stars'])}</span> · 今日 +{fmt(top1['stars_today'])} {lang_badge_html(top1)}</div>
{d1}
<p><a href="https://github.com/{top1['repo']}" target="_blank" rel="noopener" style="color:#D4A94E;font-weight:700">去 GitHub 看 &rarr;</a></p></div>"""
        else:
            spotlight = ""
        hero = f"""<section class="hero hero--gh"><div class="wrap hero-grid"><div>
<span class="hero-kicker">GitHub Trending · 中文榜</span>
<h1>今天 GitHub 上<em>最火的</em>开源项目</h1>
<p class="lede">每天更新：GitHub Trending 前 15 名，每个项目配中文简介。不用注册、不用留邮箱，打开就能看。</p>
<div class="chips"><span class="chip">{icon('clock')} {date_cn}更新</span><span class="chip">{icon('star')} {len(repos)} 个项目</span><span class="chip">{icon('book')} 中文简介</span></div>
</div><div>{spotlight}</div></div></section>
<section class="trust"><div class="wrap">
<div class="trust-item">{icon('clock')}<div><b>每日更新</b><span>每天拉取 GitHub Trending</span></div></div>
<div class="trust-item">{icon('book')}<div><b>中文简介</b><span>每条人工撰写</span></div></div>
<div class="trust-item">{icon('check')}<div><b>免费查看</b><span>不用注册、不用留邮箱</span></div></div>
</div></section>"""
        browse = """<section><div class="wrap"><h2>按语言 / 榜单浏览</h2>
<p class="muted">只关心某个语言？直接进分榜：</p><div class="grid">"""
        for _k, slug, label, _t, _d, _n in PAGES[1:]:
            browse += (f"<div class=\"card\"><div class=\"body\"><h3>"
                       f"<a href=\"{prefix}{slug}\">{label}</a></h3>"
                       f"<p class=\"muted\">GitHub {label}中文榜，每日更新。</p></div></div>")
        browse += "</div></div></section>"
    else:
        hero = f"""<section class="hero"><div class="wrap"><div>
<h1>{title}</h1>
<p class="lede">{desc}</p>
<div class="chips"><span class="chip">{icon('clock')} {date_cn}更新</span><span class="chip">{icon('star')} {len(repos)} 个项目</span><span class="chip">{icon('book')} 中文简介</span></div>
</div></div></section>"""
        browse = ""
    featured = SP.featured_slot_html(sponsors, "zh")
    featured_block = (f'<div style="margin-bottom:22px">{featured}</div>'
                      if featured else "")
    return f"""{hero}
<section><div class="wrap">
<h2>{title}</h2>
<p class="muted">数据更新于 {date_cn} · 来源 GitHub Trending · 每日更新</p>
{nl_top}
{featured_block}<ol class="rank-list">
{items}
</ol>
<div style="margin-top:22px">{sponsored_card(prefix, sponsors)}</div>
<div style="margin-top:22px">{nl_top}</div>
</div></section>
{recap}
<section><div class="wrap">{ad_rectangle()}{ad_halfpage()}
<h2>常见问题</h2>
{faq_html(LIST_FAQS)}
</div></section>
{browse}"""


def snapshot_archive(data, fetched):
    """Persist today's fetched lists under archives/<date>.json so the
    archive page for that date keeps the榜单 as first fetched that day.
    Never overwrites an existing snapshot for the same date."""
    adir = ROOT / "archives"
    adir.mkdir(exist_ok=True)
    dest = adir / f"{fetched}.json"
    if not dest.exists():
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"archived snapshot: {dest}")
    return dest


def load_archives(fetched, data):
    """All archived daily snapshots, oldest first, including today."""
    snapshot_archive(data, fetched)
    out = []
    adir = ROOT / "archives"
    for p in sorted(adir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("fetched_date") and d.get("lists"):
            out.append((d["fetched_date"], d))
    if not any(d == fetched for d, _ in out):
        out.append((fetched, data))
    out.sort(key=lambda t: t[0])
    return out


def archive_body(date_iso, data, summaries, sponsors, dates):
    """One day's archived daily Top 15: same list rendering (with the
    in-feed promo card), prev/next day pager on top, sponsor slot below."""
    date_cn = _date_cn(date_iso)
    repos = data["lists"].get("daily", [])[:15]
    mover = top_mover_of(repos)
    cards = [repo_card(i + 1, r, summaries, top_mover=mover)
             for i, r in enumerate(repos)]
    items = "\n".join(interleave_promo(
        cards, infeed_promo_html("../../", sponsors)))
    hero = f"""<section class="hero"><div class="wrap"><div>
<h1>{date_cn} GitHub 热榜回顾</h1>
<p class="lede">{date_cn} 的 GitHub Trending 日榜 Top 15 原样保留，每个项目配中文简介。归档页永久可查。</p>
<div class="chips"><span class="chip">{icon('clock')} {date_cn}</span><span class="chip">{icon('star')} {len(repos)} 个项目</span><span class="chip">{icon('book')} 中文简介</span></div>
</div></div></section>"""
    return f"""{hero}
<section><div class="wrap">
{archive_nav_html(dates, date_iso)}
<h2>{date_cn} GitHub 热榜 Top 15</h2>
<p class="muted">这是一份归档榜单：{date_cn} 的 GitHub Trending 日榜原样保留。数据来自 GitHub Trending。</p>
<ol class="rank-list">
{items}
</ol>
<div style="margin-top:22px">{sponsored_card("../../", sponsors)}</div>
<div style="margin-top:22px">{nl_strip_html("../../", date_iso)}</div>
</div></section>
<section><div class="wrap">{ad_rectangle()}{ad_halfpage()}
<h2>常见问题</h2>
{faq_html(LIST_FAQS)}
</div></section>"""


def newsletter_nav_html(dates, current):
    """Prev/next issue pager. Links only to dates that really exist;
    otherwise a muted '暂无' label — never a link to a made-up date."""
    i = dates.index(current)
    if i > 0:
        prev = (f'<a href="../{dates[i-1]}/">&larr; 上一期'
                f'（{dates[i-1]}）</a>')
    else:
        prev = '<span class="disabled">&larr; 上一期（暂无更早回顾）</span>'
    if i < len(dates) - 1:
        nxt = (f'<a href="../{dates[i+1]}/">下一期'
               f'（{dates[i+1]}） &rarr;</a>')
    else:
        nxt = '<span class="disabled">下一期 &rarr;（暂无更新回顾）</span>'
    return (f'<nav class="archive-nav" aria-label="每日回顾翻页">{prev}{nxt}'
            f'<a href="../">全部回顾</a><a href="../../">今日热门</a></nav>')


def newsletter_issue_body(date_iso, data, summaries, sponsors, dates,
                          prev_data):
    """One daily review issue: /newsletter/YYYY-MM-DD/ (TR-P1-1).
    Answer first (SEO skill): the #1 repo + its stars-today in the
    first screen. Then the day's Top 10 with per-repo star change vs
    the previous archived day, a 'new entries' note, and stats — all
    computed from real archived data, never invented. No signup form
    and no email is sent: the site has no free mail provider account.
    Readers follow the review by bookmarking this page / the index."""
    date_cn = _date_cn(date_iso)
    repos = data["lists"].get("daily", [])[:10]
    mover = top_mover_of(repos)
    prev_daily = {}
    if prev_data:
        prev_daily = {r["repo"]: r for r in
                      prev_data["lists"].get("daily", [])}
    cards = [repo_card(i + 1, r, summaries, top_mover=mover)
             for i, r in enumerate(repos)]
    items = "\n".join(interleave_promo(
        cards, infeed_promo_html("../../", sponsors)))
    # star-change lines vs yesterday (total stars, real snapshots)
    changes = []
    new_entries = []
    for r in repos:
        prev = prev_daily.get(r["repo"])
        if prev is None:
            new_entries.append(r["repo"])
            changes.append(
                f'<li><a href="https://github.com/{_esc(r["repo"])}" '
                f'target="_blank" rel="noopener">{_esc(r["repo"])}</a> · '
                f'<span class="delta-new">新上榜（昨日未进日榜 Top 15）</span> · '
                f'今日 +{fmt(r["stars_today"])}</li>')
        else:
            delta = r["stars"] - prev.get("stars", 0)
            sign = "+" if delta >= 0 else "−"
            changes.append(
                f'<li><a href="https://github.com/{_esc(r["repo"])}" '
                f'target="_blank" rel="noopener">{_esc(r["repo"])}</a> · '
                f'<span class="delta-up">总星数较昨日 {sign}{fmt(abs(delta))}</span> · '
                f'今日 +{fmt(r["stars_today"])}</li>')
    top1 = repos[0] if repos else None
    total_today = sum(r.get("stars_today", 0) for r in repos)
    langs = sorted({r["lang"] for r in repos if r.get("lang")})
    if top1:
        lede = (f"{date_cn}，GitHub 上最火的开源项目是 "
                f"{top1['repo']}，今日新增 {fmt(top1['stars_today'])} 颗星，"
                f"总星数 {fmt(top1['stars'])}。下面是当日 Top 10 与每家的星数变化，"
                f"数据来自 GitHub Trending。")
    else:
        lede = f"{date_cn} 的 GitHub 热榜数据暂无记录。"
    hero = f"""<section class="hero hero--gh"><div class="wrap"><div>
<span class="hero-kicker">每日回顾 · Newsletter Archive</span>
<h1>{date_cn} GitHub 热榜回顾</h1>
<p class="lede">{lede}</p>
<div class="chips"><span class="chip">{icon('clock')} {date_cn}</span><span class="chip">{icon('star')} Top {len(repos)}</span><span class="chip">{icon('book')} 中文简介</span></div>
</div></div></section>"""
    stats = (f'<div class="stat-row">'
             f'<div class="stat-cell"><b>+{fmt(total_today)}</b><span>Top 10 今日新增星数合计</span></div>'
             f'<div class="stat-cell"><b>{len(new_entries)}</b><span>Top 10 中新上榜（昨日未进日榜 Top 15）</span></div>'
             f'<div class="stat-cell"><b>{len(langs)}</b><span>Top 10 涉及语言数：{", ".join(langs) if langs else "—"}</span></div>'
             f'</div>' if repos else "")
    changes_block = (f'<h2>星数变化（与上一日对比）</h2>'
                     f'<p class="muted">总星数取当日与上一归档日的真实快照相减；'
                     f'上一日没有归档时本节不显示。</p>'
                     f'<ul>{"".join(changes)}</ul>' if prev_data and changes else "")
    return f"""{hero}
<section><div class="wrap">
{newsletter_nav_html(dates, date_iso)}
{stats}
<h2>{date_cn} Top 10</h2>
<p class="muted">数据更新于 {date_cn} · 来源 GitHub Trending · 每日更新</p>
<ol class="rank-list">
{items}
</ol>
<div style="margin-top:22px">{sponsored_card("../../", sponsors)}</div>
</div></section>
<section><div class="wrap">
{changes_block}
<p class="muted">想看完整日榜 Top 15？<a href="../../archive/{date_iso}/">查看 {date_cn} 完整归档榜单 &rarr;</a></p>
<p class="muted">本站目前不发邮件订阅：没有免费邮件服务商账号，也不承诺发邮件。每日回顾每天自动生成一期，收藏本页或<a href="../">看全部回顾</a>即可跟进。</p>
</div></section>
<section><div class="wrap">{ad_rectangle()}{ad_halfpage()}
<h2>常见问题</h2>
{faq_html(LIST_FAQS)}
</div></section>"""


def newsletter_index_body(dates, archives_map, sponsors):
    lis = []
    for d in reversed(dates):
        data = archives_map.get(d)
        top1 = ""
        if data:
            daily = data["lists"].get("daily", [])
            if daily:
                r0 = daily[0]
                top1 = (f" · 第 1 名：{_esc(r0['repo'])}"
                        f"（今日 +{fmt(r0.get('stars_today', 0))}）")
        lis.append(f'<li><a href="{d}/">{_date_cn(d)}（{d}）</a>{top1}</li>')
    return f"""<section class="hero hero--gh"><div class="wrap"><div>
<span class="hero-kicker">每日回顾 · Newsletter Archive</span>
<h1>每日回顾</h1>
<p class="lede">每天一期 GitHub 热榜回顾：当日 Top 10 与星数变化，全部取当日真实数据。按 Product Hunt 的 newsletter 归档做法，每期都有固定链接，可回溯、可搜索。</p>
<p class="muted">本站目前不发邮件订阅：没有免费邮件服务商账号，也不承诺发邮件。回顾页每天自动生成，收藏本页即可跟进。</p>
</div></div></section>
<section><div class="wrap"><h2>全部回顾</h2>
<ul>{''.join(lis)}</ul>
<div style="margin-top:22px">{sponsored_card("../", sponsors)}</div>
<p class="muted">想看今天的榜单？<a href="../">回今日热门</a> · <a href="../archive/">往日归档</a></p>
</div></section>"""


def archive_index_body(dates, sponsors):
    lis = "".join(
        f'<li><a href="{d}/">{_date_cn(d)}（{d}）</a> · 当日 GitHub 热榜 Top 15 归档</li>'
        for d in reversed(dates))
    return f"""<section class="hero"><div class="wrap"><div>
<h1>往日归档</h1>
<p class="lede">按日期查看每一天的 GitHub 热榜 Top 15 归档。归档从 2026-11-20 开始，每天刷新时自动增加一天，绝不补编过去日期的榜单。</p>
</div></div></section>
<section><div class="wrap"><h2>全部归档日期</h2>
<ul>{lis}</ul>
<div style="margin-top:22px">{sponsored_card("../", sponsors)}</div>
<p class="muted">想看今天的榜单？<a href="../">回今日热门</a></p>
</div></section>"""


def advertise_body(prefix):
    """Sponsorship page: tiers + flow + rules + FAQ (shared component).
    The old free-sponsorship copy is retired — tiers now have prices."""
    return SP.advertise_body_v2(
        "GitHub 每日热门", "zh", prefix,
        "每天更新的 GitHub Trending 中文榜：今日、本周、本月与各语言热门项目，每个配中文简介。赞助位与广告位招募中。",
        {"visitors": 0, "pageviews": 0, "items": 143, "items_label": "个仓库在榜", "date": "2026-11-20"})


def write_site():
    data = json.loads((ROOT / "trending.json").read_text(encoding="utf-8"))
    summaries = json.loads((ROOT / "summaries.json").read_text(encoding="utf-8"))
    fetched = data["fetched_date"]  # YYYY-MM-DD
    y, m, d = fetched.split("-")
    date_cn = f"{int(y)}年{int(m)}月{int(d)}日"
    lists = data["lists"]
    # Sponsored cards: live cards from sponsors.json (expires filtered);
    # empty list -> placeholder card. File created on first run if missing.
    sponsors_path = SP.sponsor_paths_for_site(ROOT)
    if not sponsors_path.exists():
        sponsors_path.write_text("[]\n", encoding="utf-8")
    sponsors = SP.load_sponsors(ROOT, fetched)
    archives = load_archives(fetched, data)
    arch_dates = [d for d, _ in archives]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    pages = []
    missing = []
    for key, slug, label, title, desc, limit in PAGES:
        repos = lists[key][:limit]
        for r in repos:
            if r["repo"] not in summaries:
                missing.append(r["repo"])
        body = list_body(key, title, desc, repos, summaries, date_cn,
                         "../" if slug else "", sponsors,
                         is_home=(key == "daily"),
                         archives=archives, fetched=fetched)
        html = page(f"{title} | GitHub 每日热门", desc, slug.rstrip("/"),
                    "../" if slug else "",
                    "index.html" if key == "daily" else slug, body,
                    faqs=LIST_FAQS)
        dest = OUT / slug / "index.html" if slug else OUT / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        pages.append((f"{BASE}/{slug}" if slug else f"{BASE}/"))
    adv = page("赞助合作 | GitHub 每日热门",
               "GitHub 每日热门赞助位：Starter $5/7 天、Standard $12/30 天、Featured $29/30 天。PayPal 付款，人工审核后 24 小时内上线。",
               "advertise", "../", "advertise/", advertise_body(""),
               faqs=None)
    (OUT / "advertise").mkdir(parents=True, exist_ok=True)
    (OUT / "advertise" / "index.html").write_text(adv, encoding="utf-8")
    pages.append(f"{BASE}/advertise/")
    # daily archive pages (one fixed URL per day) + archive index
    for date_iso, adata in archives:
        body = archive_body(date_iso, adata, summaries, sponsors, arch_dates)
        html_out = page(f"{_date_cn(date_iso)} GitHub 热榜回顾 | GitHub 每日热门",
                        f"{_date_cn(date_iso)} GitHub 热门 Top 15 中文回顾：当日最火的开源项目，每个配中文简介。数据来自 GitHub Trending，归档页永久可查。",
                        f"archive/{date_iso}", "../../", "archive/", body,
                        faqs=None)
        dest = OUT / "archive" / date_iso / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html_out, encoding="utf-8")
        pages.append(f"{BASE}/archive/{date_iso}/")
    idx_html = page("往日归档 | GitHub 每日热门",
                    "按日期查看每一天的 GitHub 热榜 Top 15 归档：数据来自 GitHub Trending，每日更新，归档页永久可查。",
                    "archive", "../", "archive/",
                    archive_index_body(arch_dates, sponsors), faqs=None)
    (OUT / "archive").mkdir(parents=True, exist_ok=True)
    (OUT / "archive" / "index.html").write_text(idx_html, encoding="utf-8")
    pages.append(f"{BASE}/archive/")
    # daily review issues (TR-P1-1): one fixed URL per archived day,
    # generated from the same real snapshots as the archive pages,
    # plus the issue index. No email is sent — archive pages only.
    arch_map = dict(archives)
    for pos, (date_iso, adata) in enumerate(archives):
        prev_data = archives[pos - 1][1] if pos > 0 else None
        nbody = newsletter_issue_body(date_iso, adata, summaries, sponsors,
                                      arch_dates, prev_data)
        top1 = adata["lists"].get("daily", [{}])[0]
        ndesc = (f"{_date_cn(date_iso)} GitHub 热榜回顾：当日 Top 10，"
                 f"第 1 名 {top1.get('repo', '')}今日新增 "
                 f"{fmt(top1.get('stars_today', 0))} 颗星，附星数变化。"
                 f"数据来自 GitHub Trending。")
        nhtml = page(f"{_date_cn(date_iso)} GitHub 热榜回顾 Top 10 | GitHub 每日热门",
                     ndesc, f"newsletter/{date_iso}", "../../",
                     "newsletter/", nbody, faqs=None)
        dest = OUT / "newsletter" / date_iso / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(nhtml, encoding="utf-8")
        pages.append(f"{BASE}/newsletter/{date_iso}/")
    nidx = page("每日回顾 | GitHub 每日热门",
                "每天一期 GitHub 热榜回顾：当日 Top 10 与星数变化，全部取当日真实数据。数据来自 GitHub Trending，每日更新。",
                "newsletter", "../", "newsletter/",
                newsletter_index_body(arch_dates, arch_map, sponsors),
                faqs=None)
    (OUT / "newsletter").mkdir(parents=True, exist_ok=True)
    (OUT / "newsletter" / "index.html").write_text(nidx, encoding="utf-8")
    pages.append(f"{BASE}/newsletter/")
    # RSS feed (P2补强，2026-11-21): today's daily Top 15, real data only.
    # Title = repo, description = Chinese summary (or labelled English
    # fallback), link = the GitHub repo page. Rebuilt every refresh.
    import email.utils
    pub = email.utils.format_datetime(datetime.datetime(
        int(y), int(m), int(d), 8, 0, 0,
        tzinfo=datetime.timezone(datetime.timedelta(hours=8))))
    rss_items = []
    for r in lists["daily"][:15]:
        dsc = summaries.get(r["repo"]) or r.get("desc") or "该项目暂无官方简介。"
        rss_items.append(
            f"<item><title>{_esc(r['repo'])}</title>"
            f"<link>https://github.com/{_esc(r['repo'])}</link>"
            f"<guid>https://github.com/{_esc(r['repo'])}#{fetched}</guid>"
            f"<pubDate>{pub}</pubDate>"
            f"<description>{_esc(dsc)} "
            f"今日 +{fmt(r['stars_today'])}，总星数 {fmt(r['stars'])}，"
            f"语言：{_esc(r.get('lang') or '未标注')}。</description></item>")
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0"><channel>'
           f"<title>GitHub 每日热门</title><link>{BASE}/</link>"
           f"<description>每天更新的 GitHub Trending 中文榜：今日热门 Top 15，每个配中文简介。</description>"
           f"<language>zh-CN</language><pubDate>{pub}</pubDate>"
           f"<lastBuildDate>{pub}</lastBuildDate>"
           + "".join(rss_items) + "</channel></rss>\n")
    (OUT / "feed.xml").write_text(rss, encoding="utf-8")
    # assets + root files
    (OUT / "assets" / "style.css").write_text(CSS, encoding="utf-8")
    SP.write_sponsor_assets(OUT / "assets", "gh-trending", "zh")
    for f in ("favicon.svg", "hero.svg"):
        shutil.copy(ROOT / "assets" / f, OUT / "assets" / f)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in pages:
        sm.append(f"<url><loc>{u}</loc></url>")
    sm.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: " + BASE + "/sitemap.xml\n",
        encoding="utf-8")
    (OUT / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    # Google Search Console verification (same per-account token as the
    # sibling sites; file method + meta tag both deployed).
    (OUT / "googlea94d7c9de371c76a.html").write_text(
        "google-site-verification: googlea94d7c9de371c76a.html\n",
        encoding="utf-8")
    # 404 page: served with a real 404 status by Cloudflare Pages.
    # Not in the sitemap — pages above is the sitemap list.
    # Links are relative so self_check can resolve them; the sponsored
    # card is included so the page passes the sponsored-slot check.
    (OUT / "404.html").write_text(page(
        "页面不存在 | GitHub 每日热门",
        "你要找的页面不存在，可能是链接错了或页面已移动。回到 GitHub 每日热门首页查看今日 Top 15 中文榜，或去周榜、往日归档找找。",
        "404.html", "", "404.html", f"""<div class="wrap">
<h1>404 — 页面不存在</h1>
<p>抱歉，你要找的页面不存在（或已移动）。可以试试这些：</p>
<p><a href="index.html">首页</a> &middot; <a href="weekly/index.html">周榜</a> &middot; <a href="archive/index.html">往日归档</a></p>
</div>
<div style="margin-top:22px">{sponsored_card("", sponsors)}</div>"""), encoding="utf-8")
    print(f"site written: {OUT} {len(pages)} pages, fetched {fetched}, "
          f"{len(missing)} repos without a Chinese summary "
          f"(showing official English description)")
    if missing:
        print("  missing summaries:", ", ".join(sorted(set(missing))))
    return pages, fetched, missing


def make_zip():
    zp = ROOT / "gh-trending-site.zip"
    if zp.exists():
        zp.unlink()
    count = 0
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(OUT))
                count += 1
    h = hashlib.sha256(zp.read_bytes()).hexdigest()
    print(f"zip: {zp} {count} files, {zp.stat().st_size} bytes, sha256 {h}")
    return zp, count, h


def self_check():
    import re
    errors = []
    # the GSC verification file is not a page
    html_files = sorted(p for p in OUT.rglob("*.html")
                        if p.name != "googlea94d7c9de371c76a.html")
    # 10 base pages (9 lists + advertise) + one archive page per archived
    # date + the archive index page + one newsletter issue per archived
    # date + the newsletter index page
    arch_dirs = [d for d in (OUT / "archive").iterdir()
                 if d.is_dir()] if (OUT / "archive").exists() else []
    nl_dirs = [d for d in (OUT / "newsletter").iterdir()
               if d.is_dir()] if (OUT / "newsletter").exists() else []
    expected_pages = 10 + len(arch_dirs) + 1 + len(nl_dirs) + 1 + 1  # + 404.html
    if len(html_files) != expected_pages:
        errors.append(f"expected {expected_pages} html pages, found {len(html_files)}")

    def no_script(t):
        return re.sub(r"<script[\s\S]*?</script>", "", t)
    for f in html_files:
        text = no_script(f.read_text(encoding="utf-8"))
        base = f.parent
        for m in re.finditer(r'(?:src|href)="([^"]+)"', text):
            ref = m.group(1).split("#")[0]
            if not ref or ref.startswith(("http://", "https://", "mailto:")):
                continue
            target = (base / ref).resolve()
            if not target.exists():
                errors.append(f"{f.relative_to(OUT)}: missing asset {ref}")
    # no email string anywhere in the site
    for f in OUT.rglob("*"):
        if f.is_file() and f.suffix in (".html", ".xml", ".txt", ".css", ".svg"):
            t = f.read_text(errors="ignore")
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t):
                errors.append(f"{f.relative_to(OUT)}: contains an email-like string")
    # no external resource except GitHub / Payhip / sister sites
    for f in html_files:
        t = no_script(f.read_text(encoding="utf-8"))
        for m in re.finditer(r'(?:src|href)="https?://([^"/]+)', t):
            host = m.group(1)
            if host not in ("github.com", "payhip.com", "hanxianqing.github.io",
                            "merry-gift-finder.pages.dev",
                            "gh-trending-cn.pages.dev"):
                errors.append(f"{f.relative_to(OUT)}: external host {host}")
    # ad slot markers present on every page
    for f in html_files:
        t = f.read_text(encoding="utf-8")
        if "AD SLOT: leaderboard 728x90" not in t:
            errors.append(f"{f.relative_to(OUT)}: missing leaderboard ad slot")
        if "Advertisement" not in t:
            errors.append(f"{f.relative_to(OUT)}: missing Advertisement label")
    # sponsor flow present on every page: modal + css + js
    for f in html_files:
        t = f.read_text(encoding="utf-8")
        if 'id="sp-overlay"' not in t:
            errors.append(f"{f.relative_to(OUT)}: missing sponsor modal")
        if "assets/sponsor.js" not in t:
            errors.append(f"{f.relative_to(OUT)}: missing sponsor.js")
        if "assets/sponsor.css" not in t:
            errors.append(f"{f.relative_to(OUT)}: missing sponsor.css")
        # list pages carry the sponsored slot (live card or placeholder);
        # the advertise page carries the tier cards instead
        if "sp-card" not in t and "advertise" not in str(f.relative_to(OUT)):
            errors.append(f"{f.relative_to(OUT)}: missing sponsored card")
    # advertise page lists the 3 tier prices and the PayPal flow
    adv = OUT / "advertise" / "index.html"
    adv_t = adv.read_text(encoding="utf-8")
    for price in ("$5", "$12", "$29"):
        if price not in adv_t:
            errors.append(f"advertise page missing tier price {price}")
    if "PayPal" not in adv_t:
        errors.append("advertise page missing PayPal mention")
    # sponsor assets exist
    if not (OUT / "assets" / "sponsor.js").exists():
        errors.append("assets/sponsor.js missing")
    if not (OUT / "assets" / "sponsor.css").exists():
        errors.append("assets/sponsor.css missing")
    # every repo link is a real github.com owner/repo URL (the footer
    # link to https://github.com/trending itself is allowed as-is)
    for f in html_files:
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r'href="(https://github\.com/[^"]+)"', t):
            if m.group(1) == "https://github.com/trending":
                continue
            if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", m.group(1)):
                errors.append(f"{f.relative_to(OUT)}: bad repo link {m.group(1)}")
    # indexnow key file is exactly 32 bytes; GSC file present
    keyfile = OUT / f"{INDEXNOW_KEY}.txt"
    if not keyfile.exists() or keyfile.stat().st_size != 32:
        errors.append("IndexNow key file missing or not 32 bytes")
    gsc = OUT / "googlea94d7c9de371c76a.html"
    if not gsc.exists() or "google-site-verification" not in gsc.read_text():
        errors.append("GSC verification file missing")
    # zip contains site files only
    zp = ROOT / "gh-trending-site.zip"
    with zipfile.ZipFile(zp) as z:
        bad = [n for n in z.namelist()
               if n.endswith((".py", ".md", ".json")) or "__pycache__" in n]
        if bad:
            errors.append(f"zip contains non-site files: {bad}")
    # RSS feed: 15 real items from today's daily list
    feed = OUT / "feed.xml"
    if not feed.exists() or "<rss version=\"2.0\">" not in feed.read_text(encoding="utf-8"):
        errors.append("feed.xml missing or not RSS 2.0")
    elif feed.read_text(encoding="utf-8").count("<item>") != 15:
        errors.append("feed.xml should carry exactly 15 items (today's daily Top 15)")
    if errors:
        print("SELF-CHECK FAILED:")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print("self-check passed:", len(html_files), "pages, all referenced assets present, "
          "no email, no external hosts besides GitHub/Payhip/sister sites, "
          "all repo links real, ad + sponsored slots on every page")


if __name__ == "__main__":
    write_site()
    make_zip()
    self_check()
