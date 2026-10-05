# Volumetric fog

Yorimichi's mist is Unreal's volumetric fog: a froxel grid around the camera that the sun and the sky light up, with
the sun's shadow maps carving light shafts through the trees. It is the settings menu's **Volumetric fog** button, on by
default; off puts the level's height fog back exactly as `setup_project.py` built it (no density: the painted
materials carry their own distance haze).

```sh
atelier play yorimichi --set 'fog=0'           # a session without it
```

## What it does

`AJapanWorld::ApplyVolumetricFog` (called by `UJapanPreferences::Apply`) sets the level's `ExponentialHeightFog`:

| Setting | Value | Why |
|---|---|---|
| Fog density / height falloff | 0.07 (`japan.FogDensity`) / 0.12 | The volumetric medium is the height fog's own: extinction `0.5 × density / 1000` per cm at the fog actor's height (sea level), halving every `1000 / falloff` cm up (83 m). The shore and the valleys are mistiest; the forest lake (75 m) has half as much. Twice as dense washed a low sun out to white. |
| Scattering distribution | 0.5 | Forward scattering: shafts and a halo toward the sun, still some from the side; 0.7 blew a low sun out. |
| Albedo / emissive | white / black | Water mist; no emissive, so the fog never glows on its own. |
| View distance | 30 m (`japan.FogDistance`) | The grid's reach, and so the veil on every distant view: beyond the grid everything is seen through all of it. 90 m put about 30% over Hidamari from the sea; 30 m puts about 10% (under 4% in the town). |
| Near fade-in | 3 m | The character never wades through the grid's nearest, blockiest slices. |
| Fog cutoff distance | the view distance | No analytic height fog beyond the grid. Volumetric fog ignores the cutoff: everything farther, the sky dome too, is seen through the grid's mist and gets no more, and the painted materials keep their own distance haze. |

Hidamari is already pale from afar, so the mist thins there: with the camera inside the town's `bounds`
(`hidamari/city.json`) the density is `japan.FogTown` (0.35) of the countryside's, blending back over 300 m outside
them (`AJapanWorld::UpdateFogDensity`, each frame; the renderer only hears of a real change).

The menu's Graphics button picks the grid: Quality uses the engine's Epic scalability values (`r.VolumetricFog.GridPixelSize 8`,
`GridSizeZ 128`), Performance its High ones (16, 64). Off sets `r.VolumetricFog 0`, so its passes don't run at all.
Point lights (arcade, plaza and tree house lanterns) keep `VolumetricScatteringIntensity 0`: unshadowed local lights
leak through walls into the fog, and shadowed ones cost about three times as much there.

The game's log `PROFILE` line reports `volumetric_fog` (the component), `volumetric_fog_cvar` and
`volumetric_fog_grid` as read back from the engine.

## Review film and stills

```sh
atelier play yorimichi -- -nofox -nosound -liveport=8863 -RenderOffscreen -ForceRes
atelier live py "TAKE='fog1'" && atelier live py - < games/yorimichi/scenarios/fog_film.py
python games/yorimichi/scenarios/fog_film_cut.py build/yorimichi/fog_film/fog.mp4 fog1 --stills
```

`fog_film.py` takes fixed views with the fog on and off, with the GPU frame time of each (`YorimichiLive.GpuFrameMs`),
then films a low morning sun: the village road, light shafts in the forest by the lake, the valley from the
overlook, running and gliding through it, Hidamari's arrival road, and the setting switched off and on in one view.

## Practice it follows

From Epic's [volumetric fog](https://dev.epicgames.com/documentation/en-us/unreal-engine/volumetric-fog-in-unreal-engine)
and [exponential height fog](https://dev.epicgames.com/documentation/en-us/unreal-engine/exponential-height-fog-in-unreal-engine)
pages and the 5.8 source (`VolumetricFog.cpp`, `HeightFogCommon.ush`, `BaseScalability.ini`):

- One medium for both fogs: tune the volumetric look with density, falloff and the extinction scale, not a separate
  density.
- Shafts come from the directional light's ordinary shadow maps; the screen-space "light shafts" bloom is not needed.
- Keep emissive black and fast-moving local lights out of the fog (`VolumetricScatteringIntensity 0`), or temporal
  reprojection leaves trails behind them.
- Grid cost grows with the voxel count: halving `GridPixelSize` quadruples it, so Performance keeps the High grid.
- Switching it off resets the fog's history; switching it back on takes a few noisy frames, not ghosting.
- Local fog volumes (`r.LocalFogVolume.RenderIntoVolumetricFog`) are the next step for pockets of mist (paddies, the
  lake at dawn); they are not used yet.
