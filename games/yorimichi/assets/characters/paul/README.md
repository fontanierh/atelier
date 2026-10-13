# Paul

The HarasValley playable boy: moss-green T-shirt, beige cargo trousers and green sneakers. Vendored from the brother's project with the operator's authorization, at the source revision recorded in `source-manifest.json`.

`Paul.glb` contains the existing fitted mesh, skin weights, UVs, embedded textures and skeleton at 1.65 m. Acquisition adds a floor root and maps the bones to Yorimichi's humanoid contract; the three extra torso/neck bones follow their parents. The source files and their checksums are recorded in the manifest. Normal builds need no HarasValley checkout, private download or MetaHuman plugin.

Build `unreal.paul_adventure unreal.paul_bike` with `atelier build yorimichi`, then select Paul in the character menu or pass `-rider=Paul`. The full adventure move set and Cairo's donor actions are baked onto his skeleton. All ten bike actions are fitted to his reach; skating uses the shared runtime retargeter. Bike contact data is staged by `data.paul` independently of the world.

Native motion and visual acceptance remain pending until the review capture.
