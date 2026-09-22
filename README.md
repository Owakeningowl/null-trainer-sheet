# Pokémon Null — Trainer Sheet

339 trainers, 1,665 Pokémon across ten gym splits, built from the Null
trainer spreadsheet. Live at
<https://owakeningowl.github.io/null-trainer-sheet/>.

Uses the Astral trainer sheet's layout, dark theme and held-item icons
(`theme/split_item_sprites.js`), so every held item is shown with its
sprite. Every fight is laid out on the same six-column grid, so tables
line up whether the trainer has one Pokémon or six.

Pokémon the switch AI treats specially carry a chip under their name:
**Support** (at most one damaging move, nothing over 75 BP — 20% to switch
out), **Regen** (Regenerator — 40% to switch out and heal a third) and
**Absorb** (an immunity ability — 75% once your move matches it). These come
from the colour-coded copy of the spreadsheet in `tools/null_roles.xlsx`.

Fights that carry a note in the spreadsheet — permanent weather and
terrain, gauntlet bounds, predamaged Pokémon, consecutive battles,
format choices — show a red marker beside the trainer's name; hover it
to read the note.

## Rebuilding

`tools/enrich_sheets.py` reads `tools/null_sheet.xlsx` (an export of the
Null trainer spreadsheet) and re-applies everything that is derived from
it: the cell notes, the fights whose teams are generated at runtime, the
six-column padding, the role chips and the sprite-id corrections in
`tools/sprite_slug_overrides.json`. It is safe to run repeatedly.

```
python3 tools/enrich_sheets.py
```

Trainer data belongs to the Pokémon Null project.
