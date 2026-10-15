# Paul

The project owner's playable boy: moss-green T-shirt, beige cargo trousers and green sneakers, 1.65 m.

`Paul.glb` (revision `tripo-body-r01`) is one skinned mesh with two 4K materials: `M_Paul_0`, the body, and `M_Paul_1`,
the head. Its rig is Tripo's auto-rig with Mixamo names, the fingers included. The export drops the 13 unweighted end
bones and renames the rest to the humanoid contract.

## How it was made

1. **References.** Four headless T-pose views of the body (`references/body/`), drawn by hand in ChatGPT from the
   boy's standing concept and turnaround. The body follows the standing concept's proportions. `references/README.md`
   gives the prompts.
2. **Body.** Tripo Studio, P2 multiview, made from the four views. It came back as one textured mesh with five
   separate fingers and a bare neck plug.
3. **Head.** The head is kept as it was: the `M_Paul_1` section of the previous `Paul.glb` (`haras-r01`). That is the
   HarasValley boy's face-sheet Tripo bust, vendored with the owner's authorization.
4. **Graft** (`../tools/paul_body_graft.py`, record in `provenance/graft.json`):
   - the body is welded, turned to face +X and scaled so the head (chin to the top of the hair) is 18% of his height;
   - the body's neck skin goes, and the head's own neck runs down under the collar, held 3 mm inside the shirt;
   - the arms' skin is brought to the face's colour.
5. **Rig** (`../tools/paul_rig.py`, record in `provenance/rig.json`). Tripo Studio rigged a single-texture export of the
   graft. Its file is fitted back onto the graft, because Tripo had re-centred it and turned it by 4 degrees. Each graft
   vertex then takes the weights of the rigged vertex at the same place, within 0.9 mm. The graft's own UVs and both
   textures stay.

Rebuilding from the sources needs the Tripo body and rigged GLBs, which are kept outside the repository. The committed
`Paul.glb` and its manifest are all a build needs.

## In the game

`character.toml` sets his export and import. `adventure.toml` sets his move-set fit: the sword carry is pushed
5.5 cm back and the glider bar is fitted to his grip span. Build `unreal.paul_pawn unreal.horses unreal.paul_horse`
with `atelier build yorimichi` (the pawn alone leaves the horse uninstalled; see [HORSE.md](../../../docs/HORSE.md)),
then pick Paul in the character menu or pass `-rider=Paul`.
