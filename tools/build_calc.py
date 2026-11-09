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

# Every owakeningowl.github.io site shares one localStorage, and the calcs there use the same keys (customsets,
# darkTheme...). This inline script, first thing in <head>, swaps window.localStorage for a view that keeps every
# key under this calc's own prefix, so sets imported or synced here never show up in another game's calc.
# On a first visit it copies from the old shared keys (which stay as they are): the settings below right away, and
# the hand-imported sets this calc can load (species, moves, item and ability all in its tables; "Save ..." sets
# skipped, the next save sync brings those back) once the calc has its tables, with their team/trash places.
import json as _json
STORAGE_PREFIX = 'nullcalc:'
STORAGE_COPY_PREFS = ['darkTheme', 'lasttimetrainer', 'pklucid_battlenotes']
STORAGE_COPY_LISTS = []
OWN_STORAGE = '''(function () {
  var P = %s, PREFS = %s, LISTS = %s, real;
  try { real = window.localStorage; real.getItem(P); } catch (e) { return; }
  if (real.getItem(P + '~prefs-copied') === null) {
    PREFS.forEach(function (k) { var v = real.getItem(k); if (v !== null && real.getItem(P + k) === null) real.setItem(P + k, v); });
    real.setItem(P + '~prefs-copied', '1');
  }
  function has(list, x) { return !list || (Array.isArray(list) ? list.indexOf(x) !== -1 : typeof list.has === 'function' ? list.has(x) : Object.prototype.hasOwnProperty.call(list, x)); }
  function loads(species, set) {
    if (!set || typeof set !== 'object' || !has(window.pokedex, species)) return false;
    var m = set.moves || [];
    for (var i = 0; i < m.length; i++) if (m[i] && m[i] !== '(No Move)' && !has(window.moves, m[i])) return false;
    return (!set.item || has(window.items, set.item)) && (!set.ability || has(window.abilities, set.ability));
  }
  function copySets() {
    if (real.getItem(P + '~sets-copied') !== null || !window.pokedex || !window.moves) return;
    var old = {}, mine = {}, ids = [], n = 0;
    try { old = JSON.parse(real.getItem('customsets') || '{}') || {}; } catch (e) {}
    try { mine = JSON.parse(real.getItem(P + 'customsets') || '{}') || {}; } catch (e) {}
    Object.keys(old).forEach(function (species) {
      Object.keys(old[species] || {}).forEach(function (name) {
        if (/^Save /.test(name) || !loads(species, old[species][name])) return;
        mine[species] = mine[species] || {};
        if (!mine[species][name]) { mine[species][name] = old[species][name]; n++; }
        ids.push(species + ' (' + name + ')');
      });
    });
    if (n) real.setItem(P + 'customsets', JSON.stringify(mine));
    LISTS.forEach(function (k) {
      var list = [];
      try { list = JSON.parse(real.getItem(k) || '[]') || []; } catch (e) {}
      list = Array.isArray(list) ? list.filter(function (id) { return ids.indexOf(id) !== -1; }) : [];
      if (list.length && real.getItem(P + k) === null) real.setItem(P + k, JSON.stringify(list));
    });
    real.setItem(P + '~sets-copied', String(n));
  }
  function touch(k) { if (k === 'customsets') try { copySets(); } catch (e) {} }
  function keys() { var out = []; for (var i = 0; i < real.length; i++) { var k = real.key(i); if (k && k.indexOf(P) === 0 && k.charAt(P.length) !== '~') out.push(k.slice(P.length)); } return out; }
  var api = {
    getItem: function (k) { touch(k); return real.getItem(P + k); },
    setItem: function (k, v) { touch(k); real.setItem(P + k, String(v)); },
    removeItem: function (k) { touch(k); real.removeItem(P + k); },
    clear: function () { keys().forEach(function (k) { real.removeItem(P + k); }); },
    key: function (n) { var k = keys()[n]; return k === undefined ? null : k; },
    get length() { return keys().length; }
  };
  var store = new Proxy(api, {
    get: function (t, k) { if (k in t) return typeof t[k] === 'function' ? t[k].bind(t) : t[k]; if (typeof k !== 'string') return undefined; touch(k); var v = real.getItem(P + k); return v === null ? undefined : v; },
    set: function (t, k, v) { touch(k); real.setItem(P + String(k), String(v)); return true; },
    has: function (t, k) { touch(k); return k in t || real.getItem(P + String(k)) !== null; },
    deleteProperty: function (t, k) { touch(k); real.removeItem(P + String(k)); return true; },
    ownKeys: function () { return keys(); },
    getOwnPropertyDescriptor: function (t, k) { touch(k); var v = real.getItem(P + String(k)); return v === null ? undefined : {value: v, enumerable: true, configurable: true, writable: true}; }
  });
  try { Object.defineProperty(window, 'localStorage', {configurable: true, enumerable: true, get: function () { return store; }}); } catch (e) {}
})();''' % (_json.dumps(STORAGE_PREFIX), _json.dumps(STORAGE_COPY_PREFS), _json.dumps(STORAGE_COPY_LISTS))


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
    html = once(html, '<meta charset="UTF-8" />\n', '<meta charset="UTF-8" />\n    <script>' + OWN_STORAGE + '</script>\n')

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
