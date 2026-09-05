import json
import requests

BASE = "https://www.convittocorreggio.edu.it"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConvittoEndpointProbe/1.0)"}
URLS = [
    f"{BASE}/circolare/feed/",
    f"{BASE}/feed/?post_type=circolare",
    f"{BASE}/?feed=rss2&post_type=circolare",
    f"{BASE}/wp-json/",
    f"{BASE}/wp-json/wp/v2/types",
    f"{BASE}/wp-json/wp/v2/circolare?per_page=5&_fields=id,date,modified,link,slug,title",
    f"{BASE}/wp-json/wp/v2/circolari?per_page=5&_fields=id,date,modified,link,slug,title",
    f"{BASE}/wp-json/wp/v2/search?subtype=circolare&per_page=5",
]

for url in URLS:
    print("\n===", url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        print("STATUS", r.status_code)
        print("FINAL", r.url)
        print("CTYPE", r.headers.get("content-type"))
        print("ETAG", r.headers.get("etag"))
        print("LASTMOD", r.headers.get("last-modified"))
        text = r.text
        if "/wp-json/" == r.url.rstrip("/") + "/":
            pass
        if url.endswith("/wp-json/") and r.ok:
            try:
                data = r.json()
                routes = sorted(k for k in data.get("routes", {}) if "circol" in k.lower())
                print("CIRCOLARE_ROUTES", json.dumps(routes, ensure_ascii=False))
            except Exception as e:
                print("JSONERR", e)
        elif "wp/v2/types" in url and r.ok:
            try:
                data = r.json()
                for key, value in data.items():
                    if "circol" in key.lower() or "circol" in json.dumps(value, ensure_ascii=False).lower():
                        print("TYPE", key, json.dumps(value, ensure_ascii=False)[:1200])
            except Exception as e:
                print("JSONERR", e)
        else:
            print("BODY", text[:1500].replace("\n", " "))
    except Exception as e:
        print("ERROR", repr(e))
