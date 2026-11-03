#!/usr/bin/env python3
"""Compare (and with --apply, update) trainer tables in src/*_split.html against the live Null
calculator's trainer sets, for the trainers named in Null's patch notes.

    python3 tools/patch_trainers.py TRAINERS.json [--apply]

TRAINERS.json = {calc trainer name: [species, level, ability, item, nature, moves], ...} as dumped
from the calculator's js/data/sets/gen9.js. Only the level / item / ability / nature / move rows of
the listed fights are touched; species, sprites and role chips are left alone (and a species
mismatch is reported instead of changed).
"""
import glob
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# patch-note fight -> (doc caption, calc trainer name)
FIGHTS = [
    ('Camper Charlie', 'Camper Charlie'),
    ('Fallarbor Courtney', 'Team Magma Admin Courtney 2'),
    ('Blackbelt Nob', 'Blackbelt Nob'),
    ('Ninja Boy Lao', 'Ninja Boy Lao'),
    ('Gym Leader Winona 1', 'Leader Winona 1'),
    ('Magma Grunt Zeldest', 'Hideout Team Magma Grunt Zeldest'),
    ('Seafloor Cavern Archie', 'Team Aqua Leader Archie 2'),
    ('Triathlete Stephin', 'Stephin & Triathlete Barron'),
    ('John & Jay', 'Old Couple John&Jay'),
    ('Pokéfan Bethany', 'Pokéfan Bethany'),
    ('Juan', 'Ex Leader Juan'),
    ('Rocket Ambush Weezing', 'Team Rocket Grunt #2'),
    ('MHO Grunt #10', 'Hideout Team Magma Grunt #10'),
    ('Youngster Des', 'Youngster Des'),
    ('Victory Road Maxie', 'Trainer Maxie'),
    ('Victory Road Archie', 'Trainer Archie'),
    ('SFC Shelly', 'Team Aqua Admin Shelly 2'),
    ('Reli & Ian', 'Sis And Bro Reli&Ian'),
    ('Leaf 2', 'Pokémon Trainer Leaf 2'),
    ('Noland', 'Frontier Head Noland'),
]
STATUS = {'Burned': 'Burn', 'Poisoned': 'Poison', 'Badly Poisoned': 'Poison', 'Paralyzed': 'Paralysis', 'Asleep': 'Sleep'}
ROWS = ['sprite', 'species', 'level', 'item', 'ability', 'nature', 'm1', 'm2', 'm3', 'm4']


def cells(row):
    return re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.S)


def same_species(name, aliases):
    key = lambda n: re.sub(r'[^a-z0-9]', '', n.lower())
    return any(key(name) == key(a) for a in aliases)


def text(cell):
    return html.unescape(re.sub(r'<span class="role-chip.*?</span>', '', re.sub(r'<img[^>]*>', '', cell))).strip()


def tables():
    for path in sorted(glob.glob(os.path.join(ROOT, 'src', '*_split.html'))) + [os.path.join(ROOT, 'src', 'pok_mon_league.html')]:
        doc = open(path, encoding='utf-8').read()
        for m in re.finditer(r'<table class="content-table"[^>]*>\s*<caption class="caption-content">(.*?)</caption>\s*<tbody>(.*?)</tbody>', doc, re.S):
            yield path, html.unescape(m.group(1)).strip(), m


def main(sets_path, apply):
    calc = json.load(open(sets_path))
    found = {}
    for path, caption, m in tables():
        found.setdefault(caption, []).append((path, m))
    edits = {}
    for label, trainer in FIGHTS:
        team = calc.get(trainer)
        if not team:
            print(f'!! {label}: no calc trainer {trainer!r}'); continue
        slots = []                        # a Mega / Primal / form entry right after its base is the same slot
        for t in team:
            prev = slots[-1] if slots else None
            if prev and t['species'].startswith(prev['species'] + '-') and t['level'] == prev['level'] and t.get('item') == prev.get('item'):
                prev['aliases'].add(t['species'])
                prev['abilities'].add((t.get('ability') or '').lower())
            else:
                slots.append(dict(t, aliases={t['species']}, abilities={(t.get('ability') or '').lower()}))
        team = slots
        want = [t['species'] for t in team]
        # the doc table whose species line up with the calc team
        best = None
        for caption, places in found.items():
            for path, m in places:
                rows = re.findall(r'<tr>.*?</tr>', m.group(2), re.S)
                names = [text(c) for c in cells(rows[1])][:len(team)]
                score = sum(same_species(a, t['aliases']) for a, t in zip(names, team))
                if score and (not best or score > best[0]):
                    best = (score, caption, path, m, rows)
        if not best or best[0] < max(1, len(want) - 1):
            print(f'!! {label}: no doc table matches {want}'); continue
        score, caption, path, m, rows = best
        grid = [cells(r) for r in rows]
        changes = []
        for i, mon in enumerate(team):
            if not same_species(text(grid[1][i]), mon['aliases']):
                changes.append(f'slot {i + 1}: species {text(grid[1][i])} -> {mon["species"]} (NOT changed)'); continue
            status = STATUS.get(mon.get('status') or '', '')
            new = {'level': str(mon['level']) + (f' ({status})' if status else ''), 'item': mon.get('item') or '', 'ability': mon.get('ability') or '',
                   'nature': mon.get('nature') or ''}
            moves = (mon.get('moves') or []) + [''] * 4
            for r, key in ((2, 'level'), (3, 'item'), (4, 'ability'), (5, 'nature')):
                if key == 'ability' and text(grid[r][i]).lower() in mon['abilities']:
                    continue                                    # the doc shows a Mega's ability, or only the case differs
                if text(grid[r][i]) != new[key]:
                    changes.append((r, i, f'{mon["species"]} {key}: {text(grid[r][i])} -> {new[key]}', html.escape(new[key], quote=False)))
            old_moves = [text(grid[6 + k][i]) for k in range(4)]
            if sorted(x.lower() for x in old_moves if x) != sorted(x.lower() for x in moves[:4] if x):
                for k in range(4):
                    if old_moves[k].lower() != moves[k].lower():
                        changes.append((6 + k, i, f'{mon["species"]} move {k + 1}: {old_moves[k]} -> {moves[k]}', html.escape(moves[k], quote=False)))
        print(f'== {label} = doc "{caption}" ({os.path.basename(path)})')
        for c in changes:
            print('   ', c if isinstance(c, str) else c[2])
        edits.setdefault(path, []).append((m, rows, [c for c in changes if not isinstance(c, str)]))
    if not apply:
        return
    for path, items in edits.items():
        doc = open(path, encoding='utf-8').read()
        for m, rows, changes in items:
            if not changes:
                continue
            body = m.group(2)
            new_rows = list(rows)
            for r, i, _, value in changes:
                row_cells = re.findall(r'(<t[hd][^>]*>)(.*?)(</t[hd]>)', new_rows[r], re.S)
                parts = [a + (value if j == i else b) + c for j, (a, b, c) in enumerate(row_cells)]
                new_rows[r] = '<tr>' + ''.join(parts) + '</tr>'
            new_body = body
            for old, new in zip(rows, new_rows):
                if old != new:
                    assert new_body.count(old) == 1, 'row not unique'
                    new_body = new_body.replace(old, new)
            assert doc.count(body) == 1
            doc = doc.replace(body, new_body)
        open(path, 'w', encoding='utf-8').write(doc)
        print('wrote', os.path.relpath(path, ROOT))


if __name__ == '__main__':
    main(sys.argv[1], '--apply' in sys.argv)
