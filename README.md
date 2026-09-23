# Pokémon Null — Trainer Sheet

339 trainers, 1,665 Pokémon across ten gym splits, built from the Null
trainer spreadsheet. Live at
<https://owakeningowl.github.io/null-trainer-sheet/>.

Uses the Astral trainer sheet's layout, dark theme and held-item icons
(`theme/split_item_sprites.js`), so every held item is shown with its
sprite. Every fight is laid out on the same six-column grid, so tables
line up whether the trainer has one Pokémon or six.

Pokémon the switch AI treats specially carry a chip under their name. Null
runs a separate mid-turn check for each class, and the chip says which way
that Pokémon moves:

| Chip | Class | |
|---|---|---|
| **Support** | at most one damaging move, nothing over 75 BP, no Imposter; in for more than 1 turn | 20% out |
| **Regen** | Regenerator — heals a third on the way out | 40% out |
| **Weather** | its weather-setting ability has expired; in for more than 1 turn | 20% out |
| **Hero** | Palafin, slower and about to be OHKO'd | always out |
| **Absorb** | your move type feeds its immunity ability | 75% **in** |

**Avoid Switch** blocks Support, Regen, Weather and Terrain outright. It is
active while the AI holds a stat boost, has a KO available, or the player
carries Pursuit, a phazing move (Roar, Whirlwind, Dragon Tail, Circle
Throw) or an OHKO move. Absorb and Hero ignore it. Nothing switches to a
Pokémon whose switch-in score is negative.

Support sits in two systems. Beyond the 20% chance its active Pokémon
walks, a benched Support gets **+2 to its post-KO switch-in score, 10% of
the time** (unless it is already at −1), which makes the AI likelier to
send it in. Mid-turn switches pick their replacement from that same score,
so the bonus applies there too.

Terrain setters carry no chip. The Ability cell is highlighted instead,
since "Psychic Surge" already says which terrain.

Absorb runs the other way from the rest. `FindMonThatAbsorbsOpponentsMove`
reads the ability off `party[i]` and writes the winner to
`AI_monToSwitchIntoId`, and it returns early when the Pokémon already on
the field is the one holding the ability — so an Absorb mon is what the AI
answers you with, and it never runs from the move it absorbs.

Every class is worked out from the sheet's own data — abilities, moves and
base powers in `tools/move_power.json` — rather than marked by hand. Moves
whose power is decided at run time don't count against the 75 BP ceiling.
`tools/null_roles.xlsx` is the hand-coloured copy they were cross-checked
against; nothing reads it at build time.

Fights that carry a note in the spreadsheet — permanent weather and
terrain, gauntlet bounds, predamaged Pokémon, consecutive battles,
format choices — show a red marker beside the trainer's name; hover it
to read the note.

The home page also carries a **What stops setup** reference: what Unaware,
the Haze family and phazing moves do to each setup move in the AI's move
scoring, and the caveats around it (a −20 is a heavy penalty, not a hard
block; the counter only counts on the Pokémon being targeted).

## Sheet / Dex / Calc

A bar at the top switches between the trainer sheet, the Pokédex and the
damage calculator. Both tools are iframes that are built once and from then
on only hidden, and the split pages are swapped in over `fetch` rather than
navigated to — so whatever you have typed into the calculator survives
moving around the sheet, and neither tool is ever loaded twice.

`src/calc.html` and `src/dex.html` are served from here so they can be
themed and defaulted to dark; their assets still come from
`nullcalc.pokemon0null.workers.dev` and `nulldex.pokemon0null.workers.dev`.
The dex keeps its own theme control but its navigation bar is hidden, since
this page already has one. Both remember a theme you pick afterwards.

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
