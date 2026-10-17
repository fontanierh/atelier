# Eight-view head comparison

The current best setup and later low-poly/UV/mask experiments are in the
[TRELLIS reconstruction gallery](TRELLIS_HEAD_RETOPO_GALLERY.md). This page retains
the earlier 24-recipe comparison, whose selected dense head is now a historical
geometry-preserving baseline. The original sources remain retained.

24 actual generated/material variants, five independent native neural geometries.
[Ranking and measurements](MESHAXIOM_HEAD_QUALITY.md) · [Apple Silicon recipes](APPLE_HEAD_MODELS.md).
Every sheet contains both profiles, front three-quarter views, rear, top and underside.
All use the same framing rule and semantic yaw/pitch labels. TRELLIS records a -90-degree
camera-yaw offset for its different face-forward axis; the mesh is unchanged.

The selected corrected-normal, unlit and extra lit-control sheets capture the actual WebGL model canvas
with matched cameras and lights. The other CPU sheets compare base color without
relighting. TRELLIS uses native learned
RGB baked to vertex colors, with uniform roughness/metallic values in its GLB preview;
its native PBR field's material variation is omitted. MeshAxiom learned-PBR GLBs retain
their metallic/roughness map for interactive inspection. Ranking is qualitative.
The selected result corrects shading normals with automatic coincident seams; its
ordered geometric triangles and corner colors remain exact. Gray views show the
remaining raw surface defects. The old unlit workaround bypasses lighting.

<details open>
<summary>Selected: TRELLIS768 + 16-iteration corrected lit normals (WebGL)</summary>

![Selected lit head: eight views](https://raw.githubusercontent.com/fontanierh/atelier/06f5ea59fa5d4ab5d4d48cf150a644d85215661c/head-trellis768-lit-normal16.png)

</details>

<details>
<summary>Control: TRELLIS768 + sign-independent normal tensors/seams, zero diffusion (WebGL)</summary>

![Zero-iteration lit normal control: eight views](https://raw.githubusercontent.com/fontanierh/atelier/06f5ea59fa5d4ab5d4d48cf150a644d85215661c/head-trellis768-lit-normal0.png)

</details>

<details>
<summary>Former workaround: TRELLIS768 native colors + unlit material (WebGL)</summary>

![Unlit diagnostic: eight actual WebGL views](https://raw.githubusercontent.com/fontanierh/atelier/b2b77f278b6758a649cc9cbcfe7da5b2d29b6cbb/head-trellis768-webgl-unlit.png)

</details>

<details>
<summary>Raw lit TRELLIS cascade768 baseline: base-color comparison, 11,386,792 untouched triangles</summary>

![Raw TRELLIS cascade768: eight base-color views](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-trellis-cascade768-native-color.png)

</details>

<details>
<summary>2. Compact choice: MeshAxiom native image1024 PBR + original front</summary>

![2. Compact choice: MeshAxiom native image1024 PBR + original front](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-native-image1024-front-hybrid.png)

</details>

<details>
<summary>3. Native image512 PBR + original front</summary>

![3. Native image512 PBR + original front](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-native-pbr-front-hybrid.png)

</details>

<details>
<summary>Original UV single-photo baseline</summary>

![Original UV single-photo baseline](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-original-uv-baseline.png)

</details>

<details>
<summary>Smart UV + original photograph</summary>

![Smart UV + original photograph](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-uv-original-single.png)

</details>

<details>
<summary>Smart UV + geometry-guided front</summary>

![Smart UV + geometry-guided front](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-uv-guided-single.png)

</details>

<details>
<summary>Eight-view weighted blend: rejected</summary>

![Eight-view weighted blend: rejected](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-multiview-weighted.png)

</details>

<details>
<summary>Eight-view best-angle: rejected</summary>

![Eight-view best-angle: rejected](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-multiview-best-angle.png)

</details>

<details>
<summary>Eight-view front-first2K</summary>

![Eight-view front-first2K](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-multiview-front-first-2k.png)

</details>

<details>
<summary>Eight-view front-first4K</summary>

![Eight-view front-first4K](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-multiview-front-first-4k.png)

</details>

<details>
<summary>Front-first2K + deterministic surface completion</summary>

![Front-first2K + deterministic surface completion](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-multiview-surface-fill.png)

</details>

<details>
<summary>Projected-front guided opposite: rejected</summary>

![Projected-front guided opposite: rejected](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-guided-opposite-rejected.png)

</details>

<details>
<summary>MeshAxiom29K native + eight new references</summary>

![MeshAxiom29K native + eight new references](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-29k-native-multiview.png)

</details>

<details>
<summary>MeshAxiom29K + surface completion</summary>

![MeshAxiom29K + surface completion](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-29k-native-surface-fill.png)

</details>

<details>
<summary>Native Pixal image512 PBR</summary>

![Native Pixal image512 PBR](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-native-pixal-pbr.png)

</details>

<details>
<summary>Native image512 PBR + eight-view projection</summary>

![Native image512 PBR + eight-view projection](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-native-pbr-multiview-hybrid.png)

</details>

<details>
<summary>Native Pixal image1024 / NAF512 PBR</summary>

![Native Pixal image1024 / NAF512 PBR](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-native-image1024-pbr.png)

</details>

<details>
<summary>TRELLIS single-image512 native color</summary>

![TRELLIS single-image512 native color](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-trellis512-native-color.png)

</details>

<details>
<summary>TRELLIS two-image512: rejected cheek artifact</summary>

![TRELLIS two-image512: rejected cheek artifact](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-trellis-two-image512-rejected.png)

</details>

<details>
<summary>TRELLIS512 + original-photo overlay: feature misregistration</summary>

![TRELLIS512 + original-photo overlay: feature misregistration](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-trellis512-photo-overlay.png)

</details>

<details>
<summary>TRELLIS768 + original-photo overlay: feature misregistration</summary>

![TRELLIS768 + original-photo overlay: feature misregistration](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-trellis-cascade768-photo-overlay.png)

</details>

## Lighting control on the same raw model

This is an additional render of the raw lit baseline already listed above, not a
25th recipe. The complete binary payload is identical to the unlit diagnostic. Both
WebGL sheets use the same framing, cameras and lights. Lit surface grain remains;
the unlit material bypasses lighting instead of repairing it.

![Raw lit TRELLIS768: eight actual WebGL views](https://raw.githubusercontent.com/fontanierh/atelier/b2b77f278b6758a649cc9cbcfe7da5b2d29b6cbb/head-trellis768-webgl-lit.png)

## Selected lit normals without color

This is a gray display of the same selected corrected-normal export, not another
recipe or a geometry edit. The material responds to the same scene lights. Fine
raw pits and open surfaces remain despite the substantial reduction in shading grain.

![Selected lit normals, gray: eight views](https://raw.githubusercontent.com/fontanierh/atelier/06f5ea59fa5d4ab5d4d48cf150a644d85215661c/head-trellis768-lit-normal16-gray.png)
