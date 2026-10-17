# TRELLIS automatic reconstruction: multi-view comparison

[Best setup, ranking, measurements and commands](TRELLIS_HEAD_RETOPO.md) · [Earlier 24-recipe comparison](MESHAXIOM_HEAD_GALLERY.md)

These are actual lit WebGL renders of the completed GLBs. Each sheet contains both
profiles, two front three-quarter views, rear views, top and underside. Cameras use
semantic yaw/pitch labels and the existing TRELLIS -90-degree yaw offset. Selected
new candidates use the same lights and framing. Only the sheet background and labels
are composited; model pixels are not retouched. Mask colors are a diagnostic material.
Gray/wire modes and a light-intensity change were checked separately in the browser.

The winner is the 100K derivative; the 40K derivative is the lighter recommendation.
The 18K quad derivative loses visible eyelid and hair detail. Conservative and full
repaint use identical geometry/normals/UV/index buffers; neither clearly improves the
already clean 100K bake. All are experimental local fallbacks, lower quality than
Tripo. No same-reference Tripo model was generated for this comparison.

## Close-up and UV evidence

![Dense color filtering versus selected 100K, 40K and 18K quad head](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/retopo-closeup-comparison.png)

Left to right: dense color median (dots remain), selected 100K, compact40K, and18K
quad control (rough eyelids and hair edges). The decisive cleanup comes from the
new exterior surface, not a large repaint of the selected skin.

![Selected base color, automated regions and covered UV interiors](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/retopo-uv-masks.png)

The atlas is fragmented and wastes space; it is not an artist facial layout.
Pink is confident skin, blue confident hair, gold protected features/unknown.
Eyebrows are protected even where connected to bangs; some hair/lip boundaries and
unobserved areas remain uncertain. The maps are conservative approximations.

## Eight views of each completed candidate and control

<details open>
<summary>Selected: 99,999 triangles, 4K atlas, conservative SAM2 repair</summary>

![Selected: 99,999 triangles, 4K atlas, conservative SAM2 repair](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-clean100k-repaint.png)

</details>

<details>
<summary>Control: same 100K mesh, nearest-surface color transfer</summary>

![Control: same 100K mesh, nearest-surface color transfer](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-clean100k.png)

</details>

<details open>
<summary>Compact: 39,999 triangles, sharp 4K texture</summary>

![Compact: 39,999 triangles, sharp 4K texture](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-clean40k.png)

</details>

<details>
<summary>Control: 100K, full confident-region repaint</summary>

![Control: 100K, full confident-region repaint](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-clean100k-full.png)

</details>

<details>
<summary>Control: 40K, 16-neighbor median transfer</summary>

![Control: 40K, 16-neighbor median transfer](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-exterior40k-4k.png)

</details>

<details>
<summary>Density control: 9,092 quads / 18,184 exported triangles</summary>

![Density control: 9,092 quads / 18,184 exported triangles](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-clean18k-quads.png)

</details>

<details>
<summary>SAM2 regions: pink skin; blue hair; gold protected / unknown</summary>

![SAM2 regions: pink skin; blue hair; gold protected / unknown](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-clean100k-regions.png)

</details>

<details>
<summary>Negative control: dense color median retains skin dots</summary>

![Negative control: dense color median retains skin dots](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-head-dense-median16.png)

</details>

<details>
<summary>Rejected: direct permissive reduction; vertex-color control</summary>

![Rejected: direct permissive reduction; vertex-color control](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-meshopt-permissive.png)

</details>

<details>
<summary>Rejected: direct sloppy reduction; vertex-color control</summary>

![Rejected: direct sloppy reduction; vertex-color control](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-meshopt-sloppy.png)

</details>

<details>
<summary>Rejected: volume QuadriFlow, holes and lost facial detail</summary>

![Rejected: volume QuadriFlow, holes and lost facial detail](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-lowpoly-quad15k-filt.png)

</details>

<details>
<summary>Rejected: VDB + QuadriFlow, face collapse</summary>

![Rejected: VDB + QuadriFlow, face collapse](https://raw.githubusercontent.com/fontanierh/atelier/c556874bac13c0c9b85e79eb909d210fccbc5cf8/trellis-lowpoly-median16.png)

</details>

The direct meshoptimizer controls use vertex colors and have nonmanifold edges;
their soft/missing feature colors are not a fair full-texture comparison. Their
geometry and failed UV validation are why they were rejected. The two older volume
QuadriFlow controls also had UV/texture problems, so their sheets establish failed
shape preservation rather than the quality of a valid final texture bake.

Methods that failed before a completed, visually reviewed export are listed in the
main report rather than presented as successful models. Dense checkpoint/normal-only
baselines and the earlier MeshAxiom, Pixal3D, multiview/photo and unlit controls retain
their own eight-view sheets in the earlier gallery.
