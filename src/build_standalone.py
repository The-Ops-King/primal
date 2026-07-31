#!/usr/bin/env python3
"""
Build a single self-contained page from web/index.html.

Inlines brand.css, the webfonts (as base64 @font-face — font CDNs are blocked
in the Artifact sandbox) and data.json, then strips the document skeleton so the
result can be published as an Artifact. Output: web/standalone.html
"""
import base64
import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
FONT_CSS = ("https://fonts.googleapis.com/css2"
            "?family=Anton&family=Montserrat:wght@400;500;600;700&display=swap")
CACHE = ROOT / "data" / ".fontcache.css"


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()


def inline_fonts():
    """Download the latin subsets and return @font-face rules with base64 payloads."""
    if CACHE.exists():
        return CACHE.read_text()
    css = fetch(FONT_CSS).decode()
    rules = []
    for block in css.split("/* "):
        if not block.startswith("latin */"):
            continue
        fam = re.search(r"font-family: '([^']+)'", block).group(1)
        wt = re.search(r"font-weight: (\d+)", block).group(1)
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
        b64 = base64.b64encode(fetch(url)).decode()
        rules.append(
            f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{wt};"
            f"font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    out = "\n".join(rules)
    CACHE.write_text(out)
    return out


def main():
    html = (WEB / "index.html").read_text()
    brand = (WEB / "brand.css").read_text()
    data = json.loads((WEB / "data.json").read_text())

    # Swap the Google Fonts @import for embedded faces.
    brand = re.sub(r"@import url\([^)]+\);", inline_fonts(), brand, count=1)

    # Fold brand.css in ahead of the page's own rules.
    html = html.replace('<link rel="stylesheet" href="./brand.css">',
                        f"<style>\n{brand}\n</style>")

    # Replace the network fetch with the payload itself. The replacement goes
    # through a lambda so JSON backslash escapes are not read as regex templates.
    payload = "const DATA = " + json.dumps(data, separators=(",", ":")) + ";\nrender(DATA);"
    html, n = re.subn(
        r'fetch\("\./data\.json"\)[\s\S]*?\}\);',
        lambda _: payload,
        html, count=1,
    )
    if n != 1:
        raise SystemExit("Could not find the data.json fetch call to replace.")

    # The style guide ships as its own file and has no counterpart here.
    html = html.replace('<a href="./style-guide.html">Style guide</a>', "")

    # Lock the published page to the brand's black ground. The Artifact host
    # stamps data-theme on <html> from the viewer's claude.ai theme, which would
    # otherwise flip this to the light variant and lose the identity entirely.
    # Dropping the light token block makes that stamp a no-op. The Vercel build
    # keeps its toggle — this override is specific to the embedded page.
    html = re.sub(r':root\[data-theme="light"\]\s*\{[^}]*\}', "", html, count=1)
    html = re.sub(
        r'<a href="#" onclick="const r=document\.documentElement;[\s\S]*?</a>', "", html, count=1)

    # Strip the document skeleton — the Artifact host supplies it.
    html = re.sub(r"<!doctype html>\s*|<html[^>]*>|</html>|<body>|</body>", "", html, flags=re.I)
    html = re.sub(r"<head>|</head>", "", html, flags=re.I)
    html = re.sub(r'<meta[^>]*>', "", html, flags=re.I)

    # The charset declaration has to survive. The page carries em dashes, curly
    # quotes and check glyphs, and without it a host that serves text/html with
    # no charset falls back to windows-1252 and mangles all of them. Must land
    # inside the first 1024 bytes to be honoured, so it goes first.
    html = '<meta charset="utf-8">\n' + html.strip()

    out = WEB / "standalone.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}  ({len(html)//1024} KB)")
    print(f"  fonts embedded, {len(data['calls'])} calls inlined")


if __name__ == "__main__":
    main()
