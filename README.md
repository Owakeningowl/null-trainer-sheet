# Pokémon Null — Trainer Sheet

339 trainers, 1,665 Pokémon across ten gym splits, built from the Null
trainer spreadsheet. Live at
<https://owakeningowl.github.io/null-trainer-sheet/>.

Uses the Astral trainer sheet's layout, dark theme and held-item icons
(`theme/split_item_sprites.js`), so every held item is shown with its
sprite. Every fight is laid out on the same six-column grid, so tables
line up whether the trainer has one Pokémon or six.

Pokémon the switch AI treats specially carry a chip under their name. Null
runs a separate mid-turn switch check for each class, so a chip means *this
one leaves the field on you*, with the chance it does:

| Chip | Class | Chance |
|---|---|---|
| **Support** | at most one damaging move, nothing over 75 BP, no Imposter | 20% |
| **Regen** | Regenerator — heals a third on the way out | 40% |
| **Absorb** | an immunity ability, once your move type feeds it | 75% |
| **Weather** | its weather- or terrain-setting ability has expired | 20% |
| **Hero** | Palafin, slower and about to be OHKO'd | always |

All five are worked out from the sheet's own data — abilities, moves and
base powers in `tools/move_power.json` — rather than marked by hand.
`tools/null_roles.xlsx` is the hand-coloured copy they were cross-checked
against; nothing reads it at build time.

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
