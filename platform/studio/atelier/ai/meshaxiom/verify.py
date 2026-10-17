"""Small CPU equivalence checks against the pinned upstream operations."""
from contextlib import nullcontext
from unittest.mock import patch


def main():
    import torch
    from meshaxiom.vendor.recipe.runtime import activate_namespace
    activate_namespace('vertex')
    from meshaxiom_core.models.layers import RoPE3D
    from meshaxiom_core.diffusion.flow import RectifiedFlow
    from .apple import install_operations, sample

    rope = RoPE3D(128)
    pos = torch.tensor([[[0., 0., 0.], [511.5, 255.5, 127.5]]])
    expected = rope.cos_sin(pos)
    _, attention = install_operations(query_chunk=3)
    actual = rope.cos_sin(pos)
    assert all(torch.equal(a, b) for a, b in zip(actual, expected))
    for mask in [None, torch.rand(2, 1, 1, 17) > .2, torch.rand(2, 1, 13, 17) > .2]:
        q = torch.randn(2, 2, 13, 8)
        k = torch.randn(2, 2, 17, 8)
        v = torch.randn_like(k)
        full = torch.nn.functional.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        torch.testing.assert_close(attention(q, k, v, mask), full, rtol=1e-5, atol=1e-6)
    print('PASS: tiled attention matches full masked attention; CPU FP64 rotary tables match upstream', flush=True)

    flow, x = RectifiedFlow(), torch.randn(2, 5, 8)
    model_fn = lambda x, t: .1*x + t[:, None, None]
    uncond_fn = lambda x, t: -.05*x + .2*t[:, None, None]
    expected = flow.sample(model_fn, x.clone(), steps=20, cfg_scale=3., uncond_fn=uncond_fn)
    # CPU-only comparison: disable the adapter's GPU synchronization/autocast wrappers.
    with patch('torch.mps.synchronize'), patch('torch.autocast', side_effect=lambda *a, **kw: nullcontext()):
        actual = sample(flow, model_fn, x.clone(), steps=20, cfg=3., uncond_fn=uncond_fn,
                        label='CPU sampler comparison')
    torch.testing.assert_close(actual, expected, rtol=2e-5, atol=2e-6)
    print('PASS: sampler matches upstream DPM++2M with guidance; max error',
          float((actual-expected).abs().max()), flush=True)


if __name__ == '__main__':
    main()
