# exportleak — editing-state decoration leaking into exports

## Meta

- baseline : `master` — /home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech
- candidate: `master` — /home/user/qet-fix/build-ab/7307a59c101a/build/qelectrotech
- corpus   : /home/user/qet-fix/examples (22 project(s) exported, ['schema_indus.qet'] excluded)
- formats  : svg, png, pdf
- timeout  : 120.0s / project
- generated: 2026-08-17 18:02:14
- wall-clock (candidate export): 117.6s

## Verdict

**CLEAN** — zero leaks (candidate export contains nothing the baseline does not).

## Baseline SVG inventory (per project)

| project | folios | shapes | tag counts (top) | distinct colours |
|---|---|---|---|---|
| `741` | 1 | 790 | g×2525, circle×318, polyline×248, rect×137, text×91, path×87 | #000000, #0000ff, #ff0000, #ffffff, black |
| `ArduinoLCD` | 3 | 1356 | g×2342, path×453, polyline×323, circle×291, rect×280, text×273 | #000000, #0000ff, #0055ff, #00aaff, #55aa00, #55aa7f, #55aaff, #55ff00, #ff0000, #ffaa00, #ffffff, black |
| `Habitat-Schemas_developpes` | 5 | 1371 | g×3901, circle×451, polyline×440, rect×305, text×195, path×175 | #000000, #0000ff, #00aa00, #00ff00, #aa00ff, #aa5500, #ff0000, #ff5500, #ffff00, #ffffff, black |
| `Habitat-Unifilaire` | 1 | 719 | g×1534, circle×289, polyline×274, rect×95, text×92, path×57 | #000000, #0000ff, #ff0000, #ffffff, black |
| `Projet_vierge` | 4 | 801 | g×2859, rect×524, text×444, path×169, polyline×97, circle×11 | #000000, #0000ff, #ff0000, #ffffff, black |
| `ShellyParts` | 3 | 903 | g×1559, polyline×460, text×214, rect×203, path×134, circle×63 | #000000, #0000ff, #008000, #1e90ff, #4169e1, #4682b4, #708090, #729fcf, #808080, #87cefa, #8b0000, #babdb6, #c0c0c0, #d3d7cf, #ff0000, #ff4500, #ffd700, #ffff00, #ffffff, black |
| `affuteuse_250h` | 12 | 6671 | g×16682, circle×2809, rect×1789, text×1592, polyline×1461, path×607 | #000000, #0000ff, #808080, #c0c0c0, #ff0000, #ffffff, black |
| `cablage-eclairages_sikli-v5` | 1 | 1211 | g×3020, polyline×452, path×317, circle×242, text×229, rect×199 | #000000, #0000ff, #00ff00, #a0a0a4, #aa00ff, #ff0000, #ffaa00, #ffffff, black |
| `convertisseur` | 7 | 2681 | g×7061, circle×1096, polyline×774, rect×574, text×519, path×237 | #000000, #0000ff, #ff0000, #ffffff, black |
| `câblage-éclairages-sikli-v5` | 1 | 1211 | g×3020, polyline×452, path×317, circle×242, text×229, rect×199 | #000000, #0000ff, #00ff00, #a0a0a4, #aa00ff, #ff0000, #ffaa00, #ffffff, black |
| `grafcet` | 3 | 406 | g×1845, text×186, rect×176, polyline×111, path×72, circle×47 | #000000, #0000ff, #ff0000, #ffffff, black |
| `industrial` | 50 | 17804 | g×40084, polyline×6739, text×6509, rect×6499, circle×2782, path×1771 | #000000, #0000ff, #c0c0c0, #e8e8e8, #f9f9f9, #ff0000, #ffff00, #ffffff, black |
| `iso_sfc_example` | 2 | 559 | g×2939, rect×250, text×224, polyline×163, path×113, circle×33 | #000000, #0000ff, #00aa00, #ff0000, #ffffff, black |
| `lmdg` | 1 | 1348 | g×3656, polyline×615, circle×470, text×180, rect×151, path×106 | #000000, #0000ff, #ff0000, #ffffff, black |
| `m_000` | 19 | 6991 | g×29285, polyline×2928, text×1997, circle×1702, rect×1543, path×812 | #000000, #000080, #0000c0, #0000ff, #ff0000, #ffffff, black |
| `perceuse` | 4 | 8016 | g×22445, polyline×3478, path×2450, text×1403, circle×1104, rect×984 | #000000, #0000ff, #00ff00, #612c00, #881ca8, #a0a0a4, #a3a3a3, #c0c0c0, #c6c6c6, #d5d5d5, #d6d6d6, #ff0000, #ff00ff, #ff8000, #ffff00, #ffffff, black |
| `photovoltaique` | 1 | 1057 | g×3552, polyline×558, rect×220, path×155, text×117, circle×112 | #000000, #0000ff, #00aaff, #00ff00, #00ffff, #55aaff, #55ffff, #aa00ff, #aa55ff, #ff0000, #ff7903, #ffff00, #ffffff, black |
| `pinball_williams_em` | 1 | 1281 | g×3459, polyline×711, rect×334, path×153, text×89, circle×83 | #000000, #0000ff, #ff0000, #ffffff, black |
| `schema_unifilaire_voltaique2` | 1 | 1405 | g×4201, polyline×671, rect×270, circle×269, path×186, text×114 | #000000, #0000ff, #00aaff, #55ff00, #ff0000, #ff5500, #ffff00, #ffffff, black |
| `tableau_domestique` | 5 | 5932 | g×9875, polyline×2393, circle×1946, text×1008, rect×827, path×729 | #000000, #0000ff, #0055ff, #00ff00, #00ffff, #5500ff, #a0a0a4, #c0c0c0, #ff0000, #ffff00, #ffffff, black |
| `tremie_vibrante` | 3 | 1091 | g×3529, polyline×579, rect×278, text×258, path×120, circle×114 | #000000, #0000ff, #ff0000, #ffffff, black |
| `weneedpolonez-Polonez_MR89_wiring_diagram` | 1 | 4588 | g×14647, polyline×1855, circle×1226, rect×757, path×711, text×502 | #000000, #0000ff, #0055ff, #00ff00, #00ffff, #55ff00, #55ffff, #818181, #a0a0a4, #a2a2a2, #a6a6a6, #aa00ff, #aa5500, #dadada, #ff0000, #ff55ff, #ffaa00, #ffaaff, #ffff00, #ffffff, black |

## Coarse format deltas

Zero leaks, so every PNG/PDF delta below is zero (identical build exported twice).

