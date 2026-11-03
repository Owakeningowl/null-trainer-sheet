#!/usr/bin/env python3
"""Build js/null-save-ids.js: the ID tables the calculator's mGBA save sync needs.

    python3 tools/save/build_ids.py NULL_1.2.6.gba NullLuaV1.2.4.lua CALC_NAMES.json

Names come from Null's own mGBA Lua exporter (species, moves, items, abilities by ID; the
IDs are unchanged from 1.2.4 to 1.2.6), spelled the way the calculator spells them
(CALC_NAMES.json = the calculator's species / move / item / ability names, dumped from its
calc/data/*.js). Each species' three ability slots and its growth rate come from the ROM's
species table (36-byte entries: growth rate at +21, abilities at +24, as the Lua reads them).
"""
import json
import os
import re
import struct
import sys
import zlib

NULL126_CRC = 0x7F423462
SPECIES_INFO = 0x3E4BF0          # Null 1.2.6 gSpeciesInfo (species 0)
SPECIES_STRIDE = 36

# The Lua's spelling -> the calculator's
SPECIES_FIX = {
    'Pikachu-Cosplay': 'Pikachu', 'Pikachu-Rock-Star': 'Pikachu', 'Pikachu-Belle': 'Pikachu',
    'Pikachu-Pop-Star': 'Pikachu', 'Pikachu-PhD': 'Pikachu', 'Pikachu-Libre': 'Pikachu',
    'Pichu-Spiky-eared': 'Pichu', 'Zygarde-10': 'Zygarde-10%',
    'Floette-Eternal-Mega': 'Floette-Mega', 'Zygarde-Complete-Mega': 'Zygarde-Mega',
}
ABILITY_FIX = {'Embody Aspect (Hearthflame)': 'Embody Aspect (Heartflame)'}
NATURES = ['Hardy', 'Lonely', 'Brave', 'Adamant', 'Naughty', 'Bold', 'Docile', 'Relaxed', 'Impish', 'Lax',
           'Timid', 'Hasty', 'Serious', 'Jolly', 'Naive', 'Modest', 'Mild', 'Quiet', 'Bashful', 'Rash',
           'Calm', 'Gentle', 'Sassy', 'Careful', 'Quirky']


def lua_table(src, name):
    m = re.search(r'^' + name + r'\s*=\s*\{(.*?)\n\}', src, re.S | re.M)
    return [s.strip() for s in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))]


def norm(s):
    return re.sub(r'[^a-z0-9%]', '', s.lower())


def to_calc(names, known, fix=None):
    lookup = {norm(k): k for k in known}
    out = []
    for n in names:
        n = (fix or {}).get(n, n)
        out.append(n if not n or n in known else lookup.get(norm(n), n))
    return out


def main(rom_path, lua_path, calc_names_path, out_path):
    rom = open(rom_path, 'rb').read()
    assert zlib.crc32(rom) == NULL126_CRC, 'expects an unmodified Pokémon Null 1.2.6 ROM'
    src = open(lua_path, encoding='utf-8').read()
    calc = json.load(open(calc_names_path))

    species = [''] + to_calc(lua_table(src, 'mons'), set(calc['species']), SPECIES_FIX)        # by ID, 0 = none
    moves = to_calc(lua_table(src, 'move'), set(calc['moves']))                                # already 0-based
    items = [''] + to_calc(lua_table(src, 'item'), set(calc['items']))
    items[690] = 'Recall Charm'                                                                # renamed in 1.2.5
    abilities = ['None'] + to_calc(lua_table(src, 'abilities'), set(calc['abilities']), ABILITY_FIX)

    slots, curves = [], []
    for sp in range(len(species)):
        o = SPECIES_INFO + SPECIES_STRIDE * sp
        curves.append(rom[o + 21])
        slots.extend(struct.unpack_from('<3H', rom, o + 24))
    assert species[1] == 'Bulbasaur' and moves[1] == 'Pound' and items[1] == 'Poke Ball', 'tables out of line'

    data = {'species': species, 'moves': moves, 'items': items, 'abilities': abilities,
            'speciesAbilities': slots, 'curves': curves, 'natures': NATURES}
    unknown = sorted({s for s in species if s and s not in calc['species']})
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('/* Pokémon Null 1.2.6 save IDs for the calculator\'s mGBA sync. Built by tools/save/build_ids.py. */\n')
        f.write('window.NULL_IDS = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(f'{out_path}: {len(species) - 1} species, {len(moves) - 1} moves, {len(items) - 1} items, '
          f'{len(abilities) - 1} abilities; names the calc lacks: {unknown}')


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main(sys.argv[1], sys.argv[2], sys.argv[3], os.path.join(root, 'js', 'null-save-ids.js'))
