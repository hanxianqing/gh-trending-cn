#!/usr/bin/env python3
"""Submit this site's URLs to IndexNow (Bing + Yandex).

Usage: python3 submit_indexnow.py
Key file 7c23f31035fee53caeaa7a765cb2a8c4.txt must already be live at the
site root (build_site.py writes it). Prints the HTTP status per engine.
"""
import json
import urllib.request

HOST = "gh-trending-cn.pages.dev"
KEY = "7c23f31035fee53caeaa7a765cb2a8c4"
URLS = [f"https://{HOST}/", f"https://{HOST}/weekly/",
        f"https://{HOST}/monthly/", f"https://{HOST}/python/",
        f"https://{HOST}/javascript/", f"https://{HOST}/typescript/",
        f"https://{HOST}/rust/", f"https://{HOST}/go/",
        f"https://{HOST}/chinese/", f"https://{HOST}/advertise/"]

BODY = json.dumps({
    "host": HOST,
    "key": KEY,
    "keyLocation": f"https://{HOST}/{KEY}.txt",
    "urlList": URLS,
}).encode()

for engine in ("api.indexnow.org", "www.bing.com"):
    req = urllib.request.Request(
        f"https://{engine}/indexnow",
        data=BODY, headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(engine, resp.status)
    except urllib.error.HTTPError as e:
        print(engine, "HTTPError", e.code, e.read().decode(errors="replace")[:200])
    except Exception as e:
        print(engine, "error", e)
