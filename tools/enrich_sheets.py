#!/usr/bin/env python3
"""Post-process the generated Null trainer pages.

Three passes, all idempotent:
  1. restore trainers the parser dropped because their team is "None"
     (randomly-generated / player-copy fights)
  2. attach the spreadsheet's cell notes as Astral `data-note` markers
  3. pad every .content-table out to 6 columns so all fights render the
     same width, exactly like Astral's sheet

Inputs are the xlsx export of the Null trainer spreadsheet; the grid and
note dumps are derived from it.
"""
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


def process(sheet, data, verbose=True):
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

    open(path, 'w', encoding='utf-8').write(page)
    if verbose:
        print(f'{sheet:22s} tables={len(new_tables):4d} notes+{noted:3d} restored+{added}')
    return noted, added


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
    for sheet in PAGES:
        if sheet not in book:
            print(f'!! sheet missing from workbook: {sheet}')
            continue
        n, a = process(sheet, book[sheet])
        tn += n
        ta += a
    print(f'\ntotal: {tn} cell notes attached, {ta} trainers restored')


if __name__ == '__main__':
    main()
