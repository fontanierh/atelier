# MeshAxiom review viewer

Stage explicit public model inputs into an ignored build directory. This copies the pinned local
Three.js vendor bundle from `character_review_web/vendor`, including its notices; there is no CDN.

```sh
uv run python games/yorimichi/tools/meshaxiom_viewer.py \
  --asset recycling-bin --title 'Neighborhood recycling bin' --palette bin \
  --mesh games/yorimichi/assets/props/recycling-bin-meshaxiom/mesh.source.json \
  --model games/yorimichi/assets/props/recycling-bin-meshaxiom/recycling_bin.glb \
  --reference games/yorimichi/assets/props/recycling-bin-meshaxiom/reference.png \
  --benchmark games/yorimichi/assets/props/recycling-bin-meshaxiom/benchmark.json
uv run python -m http.server 8920 --bind 127.0.0.1 \
  --directory build/yorimichi/meshaxiom/viewer
```

The authored bin GLB requires the Blender export described in the experiment guide. A raw completed
inference `mesh.glb` may also be supplied for inspection; its bytes are retained unchanged for download.
Repeat the stage command with another `--asset` slug and its files to add a model to the selector.
The most recently staged asset becomes the default. `?asset=recycling-bin` selects a stable entry.
The viewer normalizes displayed height and axes without changing connectivity; material colors are
simple preview assignments. Triangle count comes from the loaded faces, and timings/memory come
from the supplied benchmark. No benchmark means those measurements display as unavailable.

For a UV'd or Pixel Match export, add `--render-glb` to display its actual embedded material and
texture. The Colors toggle then compares texture against gray clay on the same geometry and normals.
The GLB triangle count must equal the supplied generated JSON's count. UV or normal seams can split
exported vertices without changing the original triangle connectivity. The download always preserves
the export's exact bytes.

For tailnet access, proxy this loopback port using an available Tailscale Serve path:

```sh
tailscale serve --bg --set-path /meshaxiom http://127.0.0.1:8920
```

Preserve the existing Serve routes and use only the staged directory as the HTTP root. The server
can run under the machine's service manager for persistence; its private launch configuration and
personal tailnet hostname do not belong in the public repository. Do not serve the checkout root.

Rendering is on demand, stops when hidden and caps pixel ratio at 1.5. Only an explicitly enabled
turntable renders continuously. Orbit, zoom, wireframe, gray/color comparison and reset work on
mouse and touch layouts. Open edges can be highlighted in red, with boundary/nonmanifold
counts computed from the loaded mesh. All geometry and GLB transfers stay on the serving host/tailnet.
