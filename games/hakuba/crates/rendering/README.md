# rendering

Shared rendering commands for the game. Rigid GPU-built meshes bind their existing metadata directly in the main,
prepass and shadow passes; skinned, morphed, lightmapped and CPU-built meshes use Bevy's original command. The
renderer prepares directional shadows for 3D cameras, not the window's 2D presentation camera.
