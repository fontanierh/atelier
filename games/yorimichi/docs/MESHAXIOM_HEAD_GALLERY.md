# Eight-view head comparison

21 actual generated/material variants, five independent native neural geometries.
[Ranking and measurements](MESHAXIOM_HEAD_QUALITY.md) · [Apple Silicon recipes](APPLE_HEAD_MODELS.md).
Every sheet contains both profiles, front three-quarter views, rear, top and underside.
All use the same framing rule and semantic yaw/pitch labels. TRELLIS records a -90-degree
camera-yaw offset for its different face-forward axis; the mesh is unchanged.

These CPU sheets compare base color without relighting. TRELLIS uses native learned
RGB baked to vertex colors, with uniform roughness/metallic values in its GLB preview;
its native PBR field's material variation is omitted. MeshAxiom learned-PBR GLBs retain
their metallic/roughness map for interactive inspection. Ranking is qualitative.

<details>
<summary>1. Selected: TRELLIS native cascade768, 11,386,792 untouched triangles</summary>

![1. Selected: TRELLIS native cascade768, 11,386,792 untouched triangles](https://raw.githubusercontent.com/fontanierh/atelier/aacb1a23cf6e9b7691915d54ebf82b3f1129c3df/head-trellis-cascade768-native-color.png)

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
