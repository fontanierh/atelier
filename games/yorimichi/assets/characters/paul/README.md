# Paul

The HarasValley playable boy: moss-green T-shirt, beige cargo trousers and green sneakers. Vendored from the brother's project with the operator's authorization, at the source revision recorded in `source-manifest.json`.

`Paul.glb` contains the existing fitted mesh, skin weights, UVs, embedded textures and skeleton at 1.65 m. Acquisition adds a floor root and maps the bones to Yorimichi's humanoid contract; the three extra torso/neck bones follow their parents. The source files and their checksums are recorded in the manifest. Normal builds need no HarasValley checkout, private download or MetaHuman plugin.

His body goes through the shared character pipeline: `character.toml` sets its export and import, `adventure.toml` its move-set fit (the sword carry pushed 5.5 cm back, the glider bar fitted to his grip span). Build `unreal.paul_pawn` with `atelier build yorimichi`, then select Paul in the character menu or pass `-rider=Paul`. The full adventure move set and Cairo's donor actions are baked onto his skeleton. All ten bike actions are fitted to his reach; skating uses the shared runtime retargeter.

Open: skin shows at the back of his armpits when his arms are lowered (the shirt underarm and the arm shells beneath it deform apart); the bike pose fit; the native movement and bike checks.
