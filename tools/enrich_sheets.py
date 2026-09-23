#!/usr/bin/env python3
"""Post-process the generated Null trainer pages.

Three passes, all idempotent:
  1. restore trainers the parser dropped because their team is "None"
     (randomly-generated / player-copy fights)
  2. attach the spreadsheet's cell notes as Astral `data-note` markers
  3. pad every .content-table out to 6 columns so all fights render the
     same width, exactly like Astral's sheet
  4. correct Showdown sprite slugs (ironhands, not iron-hands) from a
     verified override table
  5. tag the Pokemon the switch AI treats specially -- Support, Regen
     and Absorb -- from the colour-coded copy of the spreadsheet

Inputs are the xlsx export of the Null trainer spreadsheet; the grid and
note dumps are derived from it.
"""
import collections
import difflib
import html
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
COLS = 6
ROW_LABELS = {'Name', 'Pokémon', 'Level', 'Held Item', 'Ability', 'Nature', 'Moves'}

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'src')
OVERRIDES = os.path.join(HERE, 'sprite_slug_overrides.json')
MOVE_POWER = os.path.join(HERE, 'move_power.json')

# Null's switch AI runs a separate mid-turn check per class. Four of them are
# static properties of the Pokemon, so they are worked out from the sheet
# itself rather than trusted to a hand-coloured copy. Order here is the order
# the chips appear.
ROLE_LABELS = [
    ('support', 'Support'),
    ('regen', 'Regen'),
    ('absorb', 'Absorb'),
    ('weather', 'Weather'),
    ('hero', 'Hero'),
]

# "an immunity ability that grants an advantage" -- the ones that heal or
# boost on the immunity, not the ones that merely nullify (Levitate,
# Bulletproof, Overcoat, Soundproof, Damp).
ABSORB_ABILITIES = {
    'Volt Absorb', 'Water Absorb', 'Dry Skin', 'Flash Fire', 'Motor Drive',
    'Lightning Rod', 'Storm Drain', 'Sap Sipper', 'Earth Eater',
    'Well-Baked Body', 'Wind Rider',
}

# One AI check covers both -- "weather or terrain setting ability, and the
# corresponding weather or terrain faded" -- but they are split here because
# what you do about it differs.
WEATHER_ABILITIES = {
    'Drought', 'Drizzle', 'Sand Stream', 'Snow Warning', 'Desolate Land',
    'Primordial Sea', 'Delta Stream', 'Orichalcum Pulse',
}

# Terrain setters get no chip; the ability itself is highlighted in the
# Ability row instead, since the ability name already says which terrain.
TERRAIN_ABILITIES = {
    'Electric Surge', 'Grassy Surge', 'Misty Surge', 'Psychic Surge',
    'Hadron Engine',
}

# Moves the doc lists as utility: they do not count toward the damaging-move
# total, and the 75 BP ceiling is not applied to them either -- which is what
# lets a Foul Play or Future Sight user still be Support.
UTILITY_MOVES = {
    'Fake Out', 'Feint', 'Upper Hand', 'Endeavor', 'Super Fang', 'Dragon Tail',
    'Circle Throw', 'Knock Off', 'Foul Play', 'Future Sight', 'Bug Bite',
    'Pollen Puff',
}

# The doc's "speed control (e.g. Rock Tomb, Glaciate)": damaging moves that
# drop the target's Speed.
SPEED_CONTROL_MOVES = {
    'Icy Wind', 'Rock Tomb', 'Mud Shot', 'Bulldoze', 'Low Sweep', 'Electroweb',
    'Glaciate', 'Bubble Beam', 'Bubble', 'Constrict', 'Drum Beating', 'Pounce',
    'Syrup Bomb', 'Bleakwind Storm',
}

# Moves whose power is worked out at run time don't trip the 75 BP ceiling
# -- Terra calls them tax evaders. Most of them already sit at 1 in the move
# table (Low Kick, Grass Knot, Gyro Ball, Heavy Slam, Flail, Return, Fling,
# Magnitude, Beat Up, Super Fang, Endeavor, Ruination, Seismic Toss...), so
# they need no help. Hard Press is the one the table stores at its ceiling
# value, and Terra confirmed it evades. The same question hangs over Eruption,
# Water Spout, Dragon Energy, Bolt Beak, Fishious Rend and Tera Starstorm, but
# exempting any of them changes no Pokemon on this sheet, so it stays open.
VARIABLE_POWER_MOVES = {
    'Hard Press',
}

SUPPORT_POWER_CEILING = 75

PAGES = {
    'Roxanne Split': 'roxanne_split.html',
    'Brawly Split': 'brawly_split.html',
    'Wattson Split': 'wattson_split.html',
    'Norman Split': 'norman_split.html',
    'Flannery Split': 'flannery_split.html',
    'Winona Split': 'winona_split.html',
    'Tate&Liza Split': 'tate_liza_split.html',
    'Steven Split': 'steven_split.html',
    'Victory Road Split': 'victory_road_split.html',
    'Pokémon League': 'pok_mon_league.html',
}



# ---------------------------------------------------------------- xlsx input

def col_index(ref):
    letters = re.match(r'[A-Z]+', ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_workbook(path):
    """Return {sheet_name: {'grid': [row_dict, ...], 'notes': {row_idx: text}}}."""
    z = zipfile.ZipFile(path)
    shared = [
        ''.join(t.text or '' for t in si.iter(f'{{{M}}}t'))
        for si in ET.fromstring(z.read('xl/sharedStrings.xml'))
    ]
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = {r.get('Id'): r.get('Target')
            for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}

    out = {}
    for sh in wb.find(f'{{{M}}}sheets'):
        if sh.get('state') in ('hidden', 'veryHidden'):
            continue
        target = rels[sh.get(R)].lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target
        ws = ET.fromstring(z.read(target))

        grid = []
        for row in ws.iter(f'{{{M}}}row'):
            idx = int(row.get('r')) - 1
            while len(grid) <= idx:
                grid.append({})
            cells = {}
            for c in row.iter(f'{{{M}}}c'):
                v = c.find(f'{{{M}}}v')
                if c.get('t') == 's' and v is not None:
                    text = shared[int(v.text)]
                elif c.get('t') == 'inlineStr':
                    text = ''.join(t.text or '' for t in c.iter(f'{{{M}}}t'))
                elif v is not None:
                    text = v.text or ''
                else:
                    continue
                text = text.strip()
                if text:
                    cells[col_index(c.get('r'))] = text
            grid[idx] = cells

        notes = {}
        relpath = target.replace('xl/worksheets/', 'xl/worksheets/_rels/') + '.rels'
        if relpath in z.namelist():
            for r in ET.fromstring(z.read(relpath)):
                if 'comments' not in r.get('Target'):
                    continue
                cx = ET.fromstring(z.read('xl/' + r.get('Target').replace('../', '')))
                for cm in cx.iter(f'{{{M}}}comment'):
                    text = ''.join(t.text or '' for t in cm.iter(f'{{{M}}}t')).strip()
                    if text:
                        row_no = int(re.search(r'\d+', cm.get('ref')).group(0))
                        notes[row_no - 1] = re.sub(r'[ \t]*\n[ \t]*', ' ', text)

        out[sh.get('name')] = {'grid': grid, 'notes': notes}
    return out


# ------------------------------------------------------------- grid readers

def trainer_rows(grid):
    """Ordered [(row_idx, raw_name, area, has_team)] for every Name row."""
    area = ''
    found = []
    for i, row in enumerate(grid):
        if list(row.keys()) == [0] and row[0] not in ROW_LABELS:
            area = row[0]
        if row.get(0) == 'Name' and row.get(1):
            species = grid[i + 2] if i + 2 < len(grid) else {}
            team = [v for k, v in sorted(species.items()) if k >= 1 and v != 'None']
            found.append((i, row[1], area, bool(team)))
    return found


def strip_tag(name):
    return re.sub(r'\s*\[[^\]]*\]\s*$', '', html.unescape(name)).strip()


# -------------------------------------------------------------- html passes

TABLE_RE = re.compile(r'<table class="content-table"[^>]*>.*?</table>', re.S)
CAPTION_RE = re.compile(r'<caption class="caption-content">(.*?)</caption>', re.S)
CELL_RE = re.compile(r'<(t[hd])\b[^>]*>.*?</\1>|<(t[hd])\b[^>]*/?>', re.S)


def pad_table(table):
    """Pad every row out to COLS cells so all tables share one width."""
    def fix_row(m):
        row = m.group(0)
        cells = CELL_RE.findall(row)
        n = len(cells)
        if n == 0 or n >= COLS:
            return row
        tag = 'th' if '<th' in row else 'td'
        filler = f'<{tag}></{tag}>' * (COLS - n)
        return row[:row.rindex('</tr>')] + filler + '</tr>'

    return re.sub(r'<tr>.*?</tr>', fix_row, table, flags=re.S)


def set_note(table, note):
    """Replace/insert the data-note attribute on a table tag."""
    open_tag = re.match(r'<table[^>]*>', table).group(0)
    stripped = re.sub(r'\s*data-note="[^"]*"', '', open_tag)
    if note:
        new = stripped[:-1] + f' data-note="{html.escape(note, quote=True)}">'
    else:
        new = stripped
    return new + table[len(open_tag):]


def get_note(table):
    m = re.search(r'data-note="([^"]*)"', re.match(r'<table[^>]*>', table).group(0))
    return html.unescape(m.group(1)) if m else ''


def placeholder_table(name, note):
    rows = ['<tr>' + '<td></td>' * COLS + '</tr>',
            '<tr>' + '<th>???</th>' * COLS + '</tr>']
    rows += ['<tr>' + '<td></td>' * COLS + '</tr>'] * 2
    tag = '<table class="content-table">'
    if note:
        tag = f'<table class="content-table" data-note="{html.escape(note, quote=True)}">'
    return (f'{tag}\n<caption class="caption-content">{html.escape(name)}</caption>\n'
            '<tbody>\n' + '\n'.join(rows) + '\n</tbody>\n</table>')


def fix_sprite_slugs(page):
    """Showdown ids are not \"lowercase with hyphens\": Iron Hands is
    ironhands, Mr. Mime-Galar is mrmime-galar, and custom Megas fall back
    to the base species. Each mapping was checked against the live sprite."""
    if not os.path.exists(OVERRIDES):
        return page, 0
    with open(OVERRIDES, encoding='utf-8') as fh:
        overrides = json.load(fh)
    hits = 0
    for old, new in overrides.items():
        needle = f'/sprites/gen5/{old}.png'
        hits += page.count(needle)
        page = page.replace(needle, f'/sprites/gen5/{new}.png')
    return page, hits


# --------------------------------------------------------------- role tags

_MOVE_POWER = None


def move_power():
    global _MOVE_POWER
    if _MOVE_POWER is None:
        with open(MOVE_POWER, encoding='utf-8') as fh:
            _MOVE_POWER = json.load(fh)
    return _MOVE_POWER


def is_support(species, ability, moves):
    """Null's Support class: at most one damaging move, nothing over 75 base
    power, no Imposter. Utility moves are skipped entirely."""
    if ability == 'Imposter':
        return False
    table = move_power()
    damaging = 0
    for name in moves:
        info = table.get(name)
        if info is None:
            raise KeyError(f'no base power recorded for {name!r}')
        if name in UTILITY_MOVES or name in SPEED_CONTROL_MOVES:
            continue
        if name in ('Surf', 'Dive') and species.startswith('Cramorant'):
            continue
        if info['status']:
            continue
        if (name not in VARIABLE_POWER_MOVES
                and info['power'] > SUPPORT_POWER_CEILING):
            return False
        damaging += 1
    return damaging <= 1


def classify(species, ability, moves):
    """Every switch-AI class this Pokemon belongs to."""
    found = []
    if is_support(species, ability, moves):
        found.append('support')
    if ability == 'Regenerator':
        found.append('regen')
    if ability in ABSORB_ABILITIES:
        found.append('absorb')
    if ability in WEATHER_ABILITIES:
        found.append('weather')
    if species.split('-')[0] == 'Palafin':
        found.append('hero')
    return found


CHIP_RE = re.compile(r'<span class="role-chip[^"]*">.*?</span>', re.S)


def read_team(table):
    """Pull (species, level, item, ability, nature, moves) out of one table."""
    rows = re.findall(r'<tr>.*?</tr>', table, re.S)
    if len(rows) < 6:
        return [], rows

    def texts(row, tag):
        return [html.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                for c in re.findall(rf'<{tag}[^>]*>(.*?)</{tag}>',
                                    CHIP_RE.sub('', row), re.S)]

    species = texts(rows[1], 'th')
    ability = texts(rows[4], 'td')
    moves = [texts(r, 'td') for r in rows[6:10]]

    team = []
    for i, name in enumerate(species):
        if not name or name == '???':
            team.append(None)
            continue
        team.append((
            name,
            ability[i] if i < len(ability) else '',
            [m[i] for m in moves if i < len(m) and m[i]],
        ))
    return team, rows


def apply_roles(page):
    """Recompute every chip from the page's own data. Idempotent: existing
    chips are stripped first, so a rerun can add, move or remove them."""
    labels = dict(ROLE_LABELS)
    order = [k for k, _ in ROLE_LABELS]
    counts = collections.Counter()

    def do_table(m):
        table = m.group(0)
        team, rows = read_team(table)
        if not team:
            return CHIP_RE.sub('', table)

        species_row = rows[1]
        cells = re.findall(r'<th([^>]*)>(.*?)</th>', species_row, re.S)
        rebuilt = []
        for i, (attrs, inner) in enumerate(cells):
            attrs = re.sub(r'\s*class="role-[^"]*"', '', attrs)
            inner = CHIP_RE.sub('', inner)
            entry = team[i] if i < len(team) else None
            if entry:
                roles = [r for r in order if r in classify(*entry)]
                if roles:
                    attrs += ' class="' + ' '.join(f'role-{r}' for r in roles) + '"'
                    for r in roles:
                        inner += (f'<span class="role-chip role-chip-{r}">'
                                  f'{labels[r]}</span>')
                        counts[r] += 1
            rebuilt.append(f'<th{attrs}>{inner}</th>')

        table = table.replace(species_row,
                              '<tr>' + ''.join(rebuilt) + '</tr>', 1)

        ability_row = rows[4]
        ability_cells = re.findall(r'<td([^>]*)>(.*?)</td>', ability_row, re.S)
        marked = []
        for attrs, inner in ability_cells:
            attrs = re.sub(r'\s*class="ability-terrain"', '', attrs)
            name = html.unescape(re.sub(r'<[^>]+>', '', inner)).strip()
            if name in TERRAIN_ABILITIES:
                attrs += ' class="ability-terrain"'
                counts['terrain'] += 1
            marked.append(f'<td{attrs}>{inner}</td>')
        return table.replace(ability_row,
                             '<tr>' + ''.join(marked) + '</tr>', 1)

    return TABLE_RE.sub(do_table, page), counts



ROLE_KEY = (
    '<div class="role-key">'
    '<span class="rk-head">Leaves the field &mdash; chance per turn</span>'
    '<span><b class="rk-support">Support</b> at most one damaging move, nothing '
    'over 75 BP &mdash; after 1 turn, 20%</span>'
    '<span><b class="rk-regen">Regen</b> Regenerator, heals a third on the way '
    'out &mdash; 40%</span>'
    '<span><b class="rk-weather">Weather</b> its weather ran out &mdash; after 1 '
    'turn, 20%</span>'
    '<span><b class="rk-terrain">Terrain setter</b> highlighted ability, once its '
    'terrain runs out &mdash; after 1 turn, 20%</span>'
    '<span><b class="rk-hero">Hero</b> Palafin, slower and about to be '
    'OHKO&rsquo;d &mdash; always</span>'
    '<span class="rk-head rk-head-in">Comes in</span>'
    '<span><b class="rk-absorb">Absorb</b> when your move type feeds its ability '
    '&mdash; 75%, and it will not leave once it is out</span>'
    '<span><b class="rk-support">Support</b> +2 to its switch-in score, 10% of '
    'the time, unless already at &minus;1</span>'
    '<span class="rk-foot"><b>Avoid Switch</b> blocks Support, Regen, Weather and '
    'Terrain outright &mdash; while the AI holds a stat boost, has a KO available, '
    'or you are carrying Pursuit, a phazing move (Roar, Whirlwind, Dragon Tail, '
    'Circle Throw) or an OHKO move, none of those four fire. Absorb and Hero '
    'ignore it. Nothing switches to a Pok&eacute;mon whose switch-in score is '
    'negative.</span>'
    '</div>'
)

def add_role_key(page):
    """Put the key under the page title. Idempotent."""
    if 'class="role-key"' in page:
        return page
    m = re.search(r'</h1>', page)
    if not m:
        return page
    return page[:m.end()] + '\n' + ROLE_KEY + page[m.end():]


# ---------------------------------------------------------- setup reference

# What the AI's move scoring does to a setup move when you hold the counter.
# -20 usually takes the move out of contention; -5 only discourages it.
# Columns: Unaware / Haze family / phazing.
SETUP_ROWS = [
    ('Swords Dance, Howl, Meditate, Sharpen, Nasty Plot, Tail Glow, Dragon '
     'Dance, Shift Gear, Hone Claws, Coil, Bulk Up, Calm Mind, Quiver Dance, '
     'Growth, Work Up, Tidy Up, Victory Dance, No Retreat, Curse (non-Ghost)',
     '&minus;20', '&minus;20', '&minus;5 in the helper, needs a backup'),
    ('Iron Defense, Harden, Barrier, Acid Armor, Cotton Guard, Defense Curl, '
     'Amnesia, Cosmic Power',
     '&minus;20', '&minus;20', '&minus;5 in the helper, needs a backup'),
    ('Power-Up Punch and other guaranteed stat-raising hits &mdash; '
     '<em>only when it is not the highest-damaging move</em>',
     '&minus;20', '&minus;20', '&mdash;'),
    ('Stockpile, Stuff Cheeks',
     '&minus;20 in the helper', '&minus;20 in the helper', '&minus;5'),
    ('Agility, Rock Polish, Autotomize',
     '&mdash;', '&minus;20', '&minus;20, needs a backup'),
    ('Flame Charge, Aqua Step, Esper Wing, Trailblaze, Scale Shot',
     '&mdash;', 'loses its +6 / +7', 'loses its bonus, needs a backup'),
    ('Double Team, Minimize',
     '&minus;20', '&minus;20', '&minus;20, needs a backup'),
    ('Shell Smash, Belly Drum, Fillet Away, Clangorous Soul, Geomancy',
     '&minus;20', '&minus;20', '&minus;20, needs a backup'),
    ('Acupressure',
     '&minus;20', '&minus;20', '&minus;20, even on its last Pok&eacute;mon'),
    ('Charge', '&mdash;', '&mdash;', '&minus;20, needs a backup'),
    ('Rapid Spin <em>(no hazards on the AI&rsquo;s side)</em>',
     '&mdash;', '&minus;20', '&minus;20, needs a backup'),
    ('Baton Pass', '&mdash;', '&mdash;',
     '&minus;20 only if the AI has no raised stat'),
    ('Accuracy-raising moves, Curse (Ghost)', '&mdash;', '&mdash;', '&mdash;'),
]

SETUP_NOTES = [
    'A &minus;20 is a heavy penalty, not a hard block. Every move starts at '
    '100, so &minus;20 leaves it at 80 and any ordinary attack outscores it. '
    'A move is only dropped once its score reaches 0. If the AI has nothing '
    'that scores above 80 &mdash; everything immune, or penalised harder '
    '&mdash; it will still set up.',
    'These are moveset checks on the Pok&eacute;mon the AI is <b>targeting</b>. '
    'It only needs to know the move: your Speed, PP, Taunt, or whether the '
    'move would even work do not matter. But the counter has to be on the '
    'Pok&eacute;mon in front of it &mdash; holding Haze on the bench does '
    'nothing, and in Doubles the partner&rsquo;s Haze or Roar does not count.',
    '<b>Needs a backup</b> means the check only counts while the AI still has '
    'another Pok&eacute;mon able to switch in. Roar and Dragon Tail stop '
    'counting on its last Pok&eacute;mon &mdash; except against Acupressure.',
    'If you threaten a one-hit KO but the AI has Focus Sash, Disguise or a '
    'Substitute up, the Nasty Plot family skips the Haze and Unaware check '
    'entirely.',
    'The &minus;5 tier discourages rather than blocks: you have Foul Play or a '
    'confusing move and the move raises Attack; you have Burning Jealousy or '
    'Alluring Voice, the AI is faster and the move raises Attack; or you have '
    'a phazing move and the AI is not on its last Pok&eacute;mon.',
]


def setup_panel():
    rows = '\n'.join(
        f'<tr><td class="ref-move">{move}</td><td>{unaware}</td>'
        f'<td>{haze}</td><td>{phaze}</td></tr>'
        for move, unaware, haze, phaze in SETUP_ROWS)
    notes = '\n'.join(f'<li>{n}</li>' for n in SETUP_NOTES)
    return f'''<div class="ref-panel" id="setup">
<h2>What stops setup</h2>
<p class="ref-intro">Every move starts at 100 and the AI scores from there.
Status moves open at +6, so a setup move sits around 106 before its viability
bonuses, against attacks somewhere in the 100&ndash;114 band. That is the
scale to read these numbers on: a <b>&minus;5 is a tiebreaker</b> that
usually does not flip the decision, a <b>&minus;20 is a veto</b> that almost
always does. Three things on your side get checked: <b>Unaware</b>, the
<b>Haze family</b> (Haze, Clear Smog, Freezy Frost, Topsy-Turvy) and
<b>phazing</b> (Roar, Whirlwind, Dragon Tail, Circle Throw).</p>
<div class="ref-compare">
<h3>Haze vs Roar &mdash; where they differ</h3>
<p>They match on Minimize and Double Team, Agility / Rock Polish /
Autotomize, the Shell Smash family, Acupressure, Rapid Spin and the Flame
Charge family. Everywhere else:</p>
<table class="ref-table ref-table-compare">
<thead><tr><th></th><th>Haze family</th><th>Roar / phazing</th></tr></thead>
<tbody>
<tr><td class="ref-move">Swords Dance, Nasty Plot, Dragon Dance, Calm Mind,
Bulk Up, Quiver Dance, Hone Claws, Coil, Growth, Work Up, Tidy Up, Victory
Dance, No Retreat, Curse, Tail Glow, Shift Gear, Howl, Meditate,
Sharpen</td><td><b>&minus;20</b></td><td>&minus;5</td></tr>
<tr><td class="ref-move">Iron Defense, Harden, Barrier, Acid Armor, Cotton
Guard, Defense Curl, Amnesia, Cosmic Power</td><td><b>&minus;20</b></td>
<td>&minus;5</td></tr>
<tr><td class="ref-move">Power-Up Punch-style Attack-raising
hits</td><td><b>&minus;20</b></td><td>nothing</td></tr>
<tr><td class="ref-move">Stockpile, Stuff Cheeks</td><td><b>&minus;20</b></td>
<td>&minus;5</td></tr>
<tr><td class="ref-move">Charge</td><td>nothing</td><td><b>&minus;20</b></td></tr>
<tr><td class="ref-move">Baton Pass</td><td>nothing</td>
<td><b>&minus;20</b> if the AI has no raised stat</td></tr>
</tbody>
</table>
<p>That first row is ~19 moves and most of what teams actually set up with,
which is why the Haze family is the better blanket. On top of that, every
&minus;20 Roar does earn &mdash; and its &minus;5 as well &mdash; lapses
once the AI is on its last Pok&eacute;mon; only Acupressure survives. The
Haze family never lapses. Roar&rsquo;s only exclusives are Charge and Baton
Pass.</p>
</div>
<table class="ref-table">
<thead><tr><th>Setup move</th><th>Unaware</th><th>Haze family</th><th>Phazing</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<ul class="ref-notes">
{notes}
</ul>
</div>'''


def add_setup_panel(path):
    """Drop the setup reference onto the home page. Idempotent."""
    page = open(path, encoding='utf-8').read()
    page = re.sub(r'<div class="ref-panel" id="setup">.*?</div>\s*(?=<script|</body)',
                  '', page, flags=re.S)
    marker = '<script src="../theme/split_item_sprites.js'
    i = page.find(marker)
    if i < 0:
        return False
    open(path, 'w', encoding='utf-8').write(
        page[:i] + setup_panel() + '\n' + page[i:])
    return True


def process(sheet, data, roles=None, verbose=True):
    path = os.path.join(SRC, PAGES[sheet])
    page = open(path, encoding='utf-8').read()

    grid, notes = data['grid'], data['notes']
    entries = trainer_rows(grid)
    grid_names = [strip_tag(n) for _, n, _, _ in entries]

    tables = TABLE_RE.findall(page)
    captions = [html.unescape(CAPTION_RE.search(t).group(1)).strip() for t in tables]

    # align the spreadsheet's trainer order to the page's table order
    sm = difflib.SequenceMatcher(None, grid_names, captions)
    pairs = {}      # grid entry index -> table index
    missing = []    # grid entry indices with no table
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                pairs[i1 + k] = j1 + k
        elif tag == 'delete':
            missing.extend(range(i1, i2))
        elif tag == 'replace':
            for k in range(min(i2 - i1, j2 - j1)):
                pairs[i1 + k] = j1 + k
            missing.extend(range(i1 + (j2 - j1), i2))

    # ---- pass 1+2: notes onto existing tables
    noted = 0
    new_tables = list(tables)
    for gi, ti in pairs.items():
        row_idx = entries[gi][0]
        cell_note = notes.get(row_idx, '')
        existing = get_note(new_tables[ti])
        # the [Double]/room tag the generator already stored stays first
        tag_note = strip_note_tag(existing, cell_note)
        merged = ' — '.join(x for x in (tag_note, cell_note) if x)
        if merged != existing:
            new_tables[ti] = set_note(new_tables[ti], merged)
        if cell_note:
            noted += 1

    # ---- pass 3: pad
    new_tables = [pad_table(t) for t in new_tables]

    # write tables back
    it = iter(new_tables)
    page = TABLE_RE.sub(lambda m: next(it), page)

    # ---- pass 1: reinsert dropped trainers
    added = 0
    missing_set = set(missing)
    for gi in sorted(missing, reverse=True):
        row_idx, raw, area, _ = entries[gi]
        name = strip_tag(raw)
        if f'>{html.escape(name)}</caption>' in page or f'>{name}</caption>' in page:
            continue
        note = notes.get(row_idx, '')
        block = placeholder_table(name, note)
        anchor_gi = max((k for k in pairs if k < gi), default=None)
        if anchor_gi is None:
            page = page.replace('<div class="container">',
                                _heading(area) + block + '\n<div class="container">', 1)
        else:
            anchor_caption = captions[pairs[anchor_gi]]
            pos = _after_table(page, anchor_caption)
            prev_area = entries[anchor_gi][2]
            # only the first trainer of a restored run carries the area heading
            run_start = (gi - 1) not in missing_set
            head = _heading(area) if area and area != prev_area and run_start else ''
            page = page[:pos] + '\n' + head + block + page[pos:]
        added += 1

    page, slug_fixes = fix_sprite_slugs(page)
    page, tagged = apply_roles(page)
    page = add_role_key(page)

    open(path, 'w', encoding='utf-8').write(page)
    if verbose:
        chips = ' '.join(f'{k}:{v}' for k, v in tagged.items()) or 'none'
        print(f'{sheet:22s} tables={len(new_tables):4d} notes+{noted:3d} '
              f'restored+{added} sprites~{slug_fixes}  {chips}')
    return noted, added, tagged


def strip_note_tag(existing, cell_note):
    """Keep only the generator's own tag from a previously-merged note."""
    if not existing:
        return ''
    for sep in (' — ',):
        if sep in existing:
            return existing.split(sep)[0].strip()
    return '' if existing == cell_note else existing.strip()


def _heading(area):
    if not area:
        return ''
    return ('<div class="container">\n'
            f'<h1 class="location">{html.escape(area)}</h1>\n'
            '<div class="line"></div>\n</div>\n')


def _after_table(page, caption):
    needle = f'<caption class="caption-content">{html.escape(caption)}</caption>'
    i = page.find(needle)
    if i < 0:
        needle = f'<caption class="caption-content">{caption}</caption>'
        i = page.find(needle)
    end = page.find('</table>', i)
    return end + len('</table>')


def main():
    xlsx = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'null_sheet.xlsx')
    book = read_workbook(xlsx)
    tn = ta = 0
    chips = collections.Counter()
    for sheet in PAGES:
        if sheet not in book:
            print(f'!! sheet missing from workbook: {sheet}')
            continue
        n, a, c = process(sheet, book[sheet])
        tn += n
        ta += a
        chips.update(c)
    print(f'\ntotal: {tn} cell notes attached, {ta} trainers restored')
    if add_setup_panel(os.path.join(SRC, 'resources.html')):
        print('setup reference panel written to resources.html')
    print('role chips: ' + ', '.join(
        f'{dict(ROLE_LABELS)[k]} {chips[k]}' for k, _ in ROLE_LABELS))


if __name__ == '__main__':
    main()
