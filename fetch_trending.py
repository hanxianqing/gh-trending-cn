#!/usr/bin/env python3
"""Fetch GitHub trending lists (HTML, no key, no login) and parse them.

GitHub's trending page has no official API; we parse the public HTML.
Structure (verified 2026-11-20): each repo is an <article class="Box-row">
with an <h2> link to /owner/repo, an optional <p> description, a
<span itemprop="programmingLanguage">, stargazers/forks links, and a
"NNN stars today" span. If GitHub redesigns the page the parser returns
too few repos and the caller must abort (never deploy a thin list).
"""
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

TRENDING = {
    "daily": "https://github.com/trending?since=daily",
    "weekly": "https://github.com/trending?since=weekly",
    "monthly": "https://github.com/trending?since=monthly",
    "python": "https://github.com/trending/python?since=daily",
    "javascript": "https://github.com/trending/javascript?since=daily",
    "typescript": "https://github.com/trending/typescript?since=daily",
    "rust": "https://github.com/trending/rust?since=daily",
    "go": "https://github.com/trending/go?since=daily",
    "chinese": "https://github.com/trending?since=daily&spoken_language_code=zh",
}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


class TrendingParser(HTMLParser):
    """Collect one dict per <article class='Box-row'>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.repos = []
        self.cur = None
        self.in_h2 = False
        self.in_desc = False
        self.in_lang = False
        self.in_stars_today = False
        self.in_stargazers = False
        self.in_forks = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "article" and "Box-row" in cls:
            self.cur = {"repo": "", "desc": "", "lang": "",
                        "stars": 0, "forks": 0, "stars_today": 0}
            return
        if self.cur is None:
            return
        if tag == "h2":
            self.in_h2 = True
        elif tag == "p" and "col-9" in cls:
            self.in_desc = True
        elif tag == "span" and a.get("itemprop") == "programmingLanguage":
            self.in_lang = True
        elif tag == "span" and "float-sm-right" in cls:
            self.in_stars_today = True
        elif tag == "a":
            href = a.get("href", "")
            if href.endswith("/stargazers"):
                self.in_stargazers = True
            elif href.endswith("/forks"):
                self.in_forks = True
            elif self.in_h2 and re.fullmatch(r"/[\w.-]+/[\w.-]+", href):
                self.cur["repo"] = href.strip("/")

    def handle_endtag(self, tag):
        if tag == "article" and self.cur is not None:
            if self.cur["repo"]:
                self.repos.append(self.cur)
            self.cur = None
        elif tag == "h2":
            self.in_h2 = False
        elif tag == "p":
            self.in_desc = False
        elif tag == "span":
            self.in_lang = False
            self.in_stars_today = False
        elif tag == "a":
            self.in_stargazers = False
            self.in_forks = False

    def handle_data(self, data):
        if self.cur is None:
            return
        t = data.strip()
        if not t:
            return
        if self.in_desc:
            self.cur["desc"] += (" " if self.cur["desc"] else "") + t
        elif self.in_lang:
            self.cur["lang"] = t
        elif self.in_stars_today:
            m = re.search(r"([\d,]+)", t)
            if m:
                self.cur["stars_today"] = int(m.group(1).replace(",", ""))
        elif self.in_stargazers:
            m = re.search(r"([\d,]+)", t)
            if m:
                self.cur["stars"] = int(m.group(1).replace(",", ""))
        elif self.in_forks:
            m = re.search(r"([\d,]+)", t)
            if m:
                self.cur["forks"] = int(m.group(1).replace(",", ""))


def parse(html):
    p = TrendingParser()
    p.feed(html)
    return p.repos


def fetch_rest_repo(full_name):
    """One unauthenticated REST call for a repo's description/topics.

    Only used when the trending page has no description for a repo.
    Unauthenticated REST limit is 60/hr; we call it at most a few times.
    """
    req = urllib.request.Request(
        f"https://api.github.com/repos/{full_name}",
        headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode())
    return {"desc": d.get("description") or "",
            "topics": d.get("topics") or [],
            "stars": d.get("stargazers_count") or 0}


def fetch_all(out_path, rest_fallback=True):
    import datetime
    try:
        from zoneinfo import ZoneInfo
        today = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except Exception:
        today = (datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(hours=8)).date()
    data = {}
    for key, url in TRENDING.items():
        html = fetch(url)
        repos = parse(html)
        print(f"{key}: {len(repos)} repos")
        if len(repos) < 5:
            raise SystemExit(
                f"ABORT: {key} parsed only {len(repos)} repos — "
                "GitHub may have redesigned trending; not deploying a thin list.")
        if rest_fallback:
            for r in repos:
                if not r["desc"]:
                    try:
                        extra = fetch_rest_repo(r["repo"])
                        r["desc"] = extra["desc"]
                        print(f"  rest fallback filled desc for {r['repo']}")
                    except Exception as e:
                        print(f"  rest fallback failed for {r['repo']}: {e}")
                    time.sleep(2)
        data[key] = repos
        time.sleep(2)
    payload = {"fetched_date": today.isoformat(),
               "lists": data}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return payload


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "trending.json"
    fetch_all(out)
    print("wrote", out)
