# Bambu Lab X2D: FDM minis and terrain (cited)

Settings, realistic print times, sourcing, and optional purchases for printing 28 to 32 mm minis
and terrain on the Bambu Lab X2D, FDM only, no resin. Specs are from retailer sheets and trade
write-ups because Bambu's own page returned 403 during research, so confirm the exact model and
firmware against Bambu's site before buying hardware. Print times are community estimates from
other Bambu models (A1 mini, P1P), not measured on the X2D: run a test plate before trusting the
schedule.

## Printer (confirmed to exist; verify details)

- Dual-nozzle enclosed FDM printer, announced around April 2026 (one source's URL says 2025, so
  confirm the date and model).
- Build volume about 256 x 256 x 260 mm with the main nozzle, a little less with both nozzles.
- Two nozzles: a direct-drive main nozzle, and an auxiliary nozzle for support material, so one
  nozzle prints the model while the other prints supports.
- Nozzle sizes listed: 0.2, 0.4, 0.6, 0.8 mm, with a 0.4 mm hardened steel nozzle included.
- Works with AMS for multi-material and multi-color. The auxiliary nozzle can hold soluble or
  easy-release supports (PVA, BVOH).
- Nozzle to 300 C, active chamber to 65 C, filtration, quiet, tool-free nozzle swaps.

## Nozzle and layer height

- 0.2 mm nozzle for hero, NPC, and boss minis: the single biggest quality jump at 28 to 32 mm.
  Layers 0.06 to 0.08 mm, 3 to 5 walls, gyroid infill 10 to 20 percent. (0.08 mm is near the flow
  floor on this nozzle, so test first.)
- 0.4 mm nozzle for crowds, Large-plus monsters, bases, and terrain. Layers 0.08 to 0.12 mm for
  minis (approaches 0.2 mm nozzle quality for less time), 0.16 to 0.20 mm for terrain.
- The main nozzle has to be physically swapped, so it cannot run 0.2 mm and 0.4 mm in the same
  print. Batch by nozzle.

## Supports and orientation

- Organic tree supports that start only from the build plate; top Z-distance about 2 to 3 times the
  layer height.
- Thin supports fail often on FDM. For tangled poses, use the auxiliary nozzle with soluble PVA or
  BVOH (depends on correct drying and a tuned profile, which was not verified), or cut the mini into
  parts, print each in a good orientation, and glue with superglue (plastic cement does not bond FDM
  plastics).
- Print minis upright, face and front forward, tilted back slightly if a cloak or weapon allows.
  Print swords and spears at a slight angle so layer lines do not run across the weak axis.

## Materials (current stock plus optional purchases)

Current stock (PLA, PETG, TPU 95A HF) covers the common cases:

- Minis: PLA (holds detail better than PETG). PETG HF works but strings more.
- Terrain: PLA for most pieces, PETG for pieces that get handled or left in a hot car.
- TPU 95A HF: flexible bases, tails, tentacles, and grippy or overland terrain. Not for fine mini
  detail.

Optional purchases, each with a reason (verify compatibility against the X2D's real specs):

- Fine-detail matte PLA in grey: better paint adhesion and fewer visible layer lines on minis. The
  clearest single upgrade for hero and boss figures.
- PVA or BVOH soluble support filament: clean supports on tangled poses using the auxiliary nozzle.
  Only worth it if you commit to that workflow.
- A 0.2 mm hardened steel hotend: if you print detailed minis regularly.
- A filament dryer: moisture caused stringing and whitening in a forum test, especially for PETG and
  TPU.

## Realistic print times (estimates, not benchmarks)

- One small or medium mini at 0.08 mm, 0.2 mm nozzle: about 3 to 6 hours (a community P1P test gave
  about 3 to 3.7 hours for a 4 to 5 cm figure).
- One mini at 0.12 mm, 0.4 mm nozzle: about 1 to 2 hours.
- A Large or boss mini: about 6 to 12 hours or more.
- A plate of 4 to 8 small minis at fine settings: roughly 12 to 24 hours (extrapolated).
- Terrain: a modular room tile 1 to 3 hours; a larger dungeon set or set piece 4 to 20 hours.
- Lead-time rule: queue mini batches 2 to 3 days ahead, and add a day for failures and cleanup.

## Sourcing and inventory

STL sources (verify current terms and FDM-friendliness per pack):

- Printables (free, good community FDM profiles), MyMiniFactory (tabletop collections),
  Thingiverse (large, uneven), Cults3D (paid and free).
- Mini Patreons: Loot Studios, Cast n Play, Printed Obsession, Artisan Guild. Most are sculpted for
  resin, so check for pre-supported or FDM-friendly files and treat as resin-first unless the pack
  says otherwise.
- Terrain: Fat Dragon Games and similar. Community FDM profiles via r/FDMminiatures.

Inventory and proxy workflow lives in the skill body (printable-minis-and-terrain). Give every
unprinted mini a "needs print by" date so the lead-time schedule surfaces it before the session.

## Sources

- https://www.solidprint3d.co.uk/wp-content/uploads/2026/04/Bambu-Lab-X2D-3d-printer-specification.pdf
- https://3dprintingindustry.com/news/bambu-lab-launches-x2d-dual-nozzle-3d-printer-targeting-reduced-post-processing-and-material-waste-251005/
- https://forum.bambulab.com/t/miniature-print-settings-quality-and-print-time/208057
- https://bestiarumgames.com/blogs/news/printing-detailed-miniatures-with-fdm
- https://makers101.com/0-4mm-nozzle-print-like-0-2mm/
