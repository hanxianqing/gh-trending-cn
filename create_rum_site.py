#!/home/hatch/workspace/custom-connectors/custom.cloudflare/.venv/bin/python
"""Create a Cloudflare Web Analytics (RUM) site for a hostname.

Usage: create_rum_site.py <hostname>
Prints the JSON response (contains the site token for the beacon).
Auth via the stored custom.cloudflare credential surrogate.
"""
import json
import sys
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

ACCOUNT = "461b5a7b4f4564a630d83f27726bc897"
API = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/rum/site_info"


def main():
    host = sys.argv[1]
    req = urllib.request.Request(API, method="POST")
    add_surrogate_to_request(req, "custom.cloudflare",
                             allowed_hosts=["api.cloudflare.com"])
    req.add_header("Content-Type", "application/json")
    req.data = json.dumps({"host": host}).encode()
    with urllib.request.urlopen(req, timeout=60) as resp:
        print(resp.read().decode())


if __name__ == "__main__":
    main()
