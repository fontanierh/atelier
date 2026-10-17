# Model implementations used by the head experiments

These adapters load the original published model weights locally. Weights are not
redistributed. The manifests bind repositories, revisions, sizes and SHA256 values.

- [AlayaLab/MeshAxiom](https://github.com/AlayaLab/MeshAxiom): native geometry and documented texture recipe.
- [TencentARC/Pixal3D](https://github.com/TencentARC/Pixal3D): supplied-shape image-conditioned texture flow.
- [Microsoft/TRELLIS.2](https://github.com/microsoft/TRELLIS.2): shape/PBR models and native generation.
- [Pixal3D-mac](https://github.com/pawel-mazurkiewicz/Pixal3D-mac): Metal/MPS kernels and model implementation.
- [trellis2mlx](https://github.com/lyonsno/trellis2mlx): MLX implementation and inference/export driver.
- [valeoai/NAF](https://github.com/valeoai/NAF): image-feature upsampling.

Only small compatibility patches are included here. Full pinned upstream sources
and their licenses are fetched into the ignored build runtime by setup. The model
repositories retain their individual weight terms. The DINO mirror has the same
SHA256 as the official DINOv3 checkpoint; it is not a replacement model.

## Pixal3D-mac source license

MIT License

Copyright (c) 2026 Tencent.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


## trellis2mlx source license

MIT License

Copyright (c) 2026 Noah Lyons

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

Note: This license covers the trellis2mlx porting code only. Upstream model
weights, checkpoints, and pretrained models are subject to their own licenses:

- TRELLIS.2 model weights: see https://github.com/microsoft/TRELLIS.2
- DINOv3 weights: Meta gated model, see https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m
- rembg (RMBG-2.0): CC BY-NC-SA 4.0

The QEM mesh simplification algorithm is adapted from pedronaugusto/mtlmesh
(cumesh), also MIT-licensed.
