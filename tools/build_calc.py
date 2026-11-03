#!/usr/bin/env python3
"""Rebuild src/calc.html from the live Pokémon Null calculator, plus this site's additions.

    python3 tools/build_calc.py [saved index.html]

Takes https://nullcalc.pokemon0null.workers.dev/ as it is served today (or a saved copy), so
trainer sets, species, moves and the calculator itself stay exactly Null's. Its scripts and
stylesheets keep loading from the calculator's own site. Added on top:
  - theme/calc-dark.css + theme/calc-astral.css (the sheet's dark Astral look), dark by default
  - js/null-save-ids.js + js/null-save.js + theme/calc-save.css: "Link mGBA save" above Team / Box
"""
import os
import re
import sys
import urllib.request

LIVE = 'https://nullcalc.pokemon0null.workers.dev/'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def version(path):
    """A short content hash, so browsers pick up a changed file."""
    import hashlib
    return hashlib.sha1(open(os.path.join(ROOT, path), 'rb').read()).hexdigest()[:8]


def once(html, old, new):
    assert html.count(old) == 1, f'expected exactly one {old!r} in the live calculator page'
    return html.replace(old, new)


def main(src=None):
    if src:
        html = open(src, encoding='utf-8').read()
    else:
        req = urllib.request.Request(LIVE, headers={'User-Agent': 'null-trainer-sheet build'})
        html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')

    html = re.sub(r'(src|href)="\./', lambda m: f'{m.group(1)}="{LIVE}', html)

    dark_link = f'<link type="text/css" rel="stylesheet" href="{LIVE}css/dark-theme.css" id="dark-theme-styles">'
    html = once(html, dark_link, dark_link + '\n'
                f'    <link type="text/css" rel="stylesheet" href="../theme/calc-dark.css?v={version("theme/calc-dark.css")}" />')
    html = once(html, "        if (localStorage.getItem('darkTheme') !== 'true') {",
                "        // Default to dark on a first visit; a later toggle still sticks.\n"
                "        if (localStorage.getItem('darkTheme') === null) {\n"
                "            localStorage.setItem('darkTheme', 'true');\n"
                "        }\n"
                "        if (localStorage.getItem('darkTheme') !== 'true') {")
    html = once(html, '</head>',
                f'    <link type="text/css" rel="stylesheet" href="../theme/calc-astral.css?v={version("theme/calc-astral.css")}" />\n'
                f'    <link type="text/css" rel="stylesheet" href="../theme/calc-save.css?v={version("theme/calc-save.css")}" />\n'
                '</head>')
    html = once(html, '</body>',
                '<script>(function(){var d=document.getElementById("dark-theme-styles");if(d) d.disabled=false;})();</script>\n'
                f'<script src="../js/null-save-ids.js?v={version("js/null-save-ids.js")}"></script>\n'
                f'<script src="../js/null-save.js?v={version("js/null-save.js")}"></script>\n'
                '</body>')

    out = os.path.join(ROOT, 'src', 'calc.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'{out}: {len(html)} bytes from {src or LIVE}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
