# rendering

Shared rendering commands for the game. Rigid GPU-built meshes bind their existing metadata directly in the main,
prepass and shadow passes, and draw from where their buffers sit, noted once per mesh when it is prepared or moves;
skinned, morphed, lightmapped and CPU-built meshes use Bevy's original commands. The
renderer prepares directional shadows for 3D cameras, not the window's 2D presentation camera.
