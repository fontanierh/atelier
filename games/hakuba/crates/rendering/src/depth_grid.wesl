// Keeps the farthest reversed depth of each grid cell: one workgroup per cell, its threads striding over the cell's
// pixels. Reversed depth is never negative, so its bits order as the depths do.
@group(0) @binding(0) var depth: texture_depth_2d;
@group(0) @binding(1) var<storage, read_write> grid: array<u32>;

const HEADER: u32 = 24u;
const GRID: vec2<u32> = vec2<u32>(64u, 36u);

var<workgroup> farthest: atomic<u32>;

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(workgroup_id) cell: vec3<u32>, @builtin(local_invocation_id) thread: vec3<u32>) {
    if all(thread.xy == vec2<u32>(0u)) {
        atomicStore(&farthest, bitcast<u32>(1.0));
    }
    workgroupBarrier();
    let size = textureDimensions(depth);
    let first = cell.xy * size / GRID;
    let past = (cell.xy + 1u) * size / GRID;
    var least = 1.0;
    for (var y = first.y + thread.y; y < past.y; y += 8u) {
        for (var x = first.x + thread.x; x < past.x; x += 8u) {
            least = min(least, textureLoad(depth, vec2<u32>(x, y), 0));
        }
    }
    atomicMin(&farthest, bitcast<u32>(max(least, 0.0)));
    workgroupBarrier();
    if all(thread.xy == vec2<u32>(0u)) {
        grid[HEADER + cell.y * GRID.x + cell.x] = atomicLoad(&farthest);
    }
}
