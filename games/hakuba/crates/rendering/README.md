# rendering

Shared rendering commands for the game. Rigid GPU-built meshes bind their existing metadata directly in the main,
prepass and shadow passes, and draw from where their buffers sit, noted once per mesh when it is prepared or moves;
skinned, morphed, lightmapped and CPU-built meshes use Bevy's original commands. Each draw fetches only the resources
the rigid path reads; Bevy's binding and draw fetch theirs only when a draw falls back to them. The
renderer prepares directional shadows for 3D cameras, not the window's 2D presentation camera.

`defaults.rs` holds the renderer settings the game always uses: the sun's two shadow cascades redraw on alternate
frames and reuse their kept maps in between (the vendored PBR renderer's `ShadowCascadeReuse`), and on the desktop the
sun's shadow map is 2048 texels and the few lights are clustered on the CPU rather than with GPU compute passes.

`depth_grid.rs` reads back a small grid of the last frame's depth, which the world uses to hide distant blocks behind
nearer things.

`forward_motion.rs` owns the forward-motion modes for the world camera. On the desktop the world camera uses `single`
by default; `compare` and `publish` are validation stages.
`HAKUBA_FORWARD_MOTION=compare` on the desktop or `?forward_motion=compare` in the browser adds a separate RG16Float motion attachment to opaque/masked
main rendering. The pinned local Bevy PBR patch supplies prior-position data and matching material outputs.
`ForwardMotionComparison` exposes that target in the render world for diagnostics. The full original prepass and
its TAA inputs remain active; this mode does not remove work or establish a frame-rate improvement. Unmarked views
retain the standard opaque pass. The comparison rejects MSAA, normal/deferred prepasses, built-in skyboxes and
main-pass resolution overrides rather than silently producing unsupported output. The regular world uses a mesh sky.

The main pass retains the existing foliage depth margin. Its visible winner can differ from the unbiased prepass
near intersections, so equal vector math does not establish equivalent temporal edge quality. Compare the two
motion targets and displayed temporal sequences before replacing any prepass output.

`HAKUBA_FORWARD_MOTION=publish` or `?forward_motion=publish` keeps the geometry prepass but substitutes the main motion
and depth into TAA. `single` also omits geometry draws in the early and late camera prepasses once the motion-transfer
pipeline is ready. The stock prepass clears, background draw, and scheduling remain intact. Neither mode changes shadow
passes. Both copy the main depth into the existing prepass depth texture and publish motion with a fullscreen
`textureLoad` pass: the existing motion texture cannot receive a raw copy. Publication completes before transparent
rendering and TAA. `forward_motion_transfer.wesl` reads one exact texel per output pixel; it does not filter,
reconstruct, or approximate motion. `single` is the desktop default; in the browser all three stay explicit while
temporal quality and performance there are validated. All marked cameras reject screen-space transmission, whose
separate draw pass has no motion attachment. `single` also rejects contact shadows and GPU occlusion culling: those
features need geometry depth before main rendering, not the completed depth published afterward.
