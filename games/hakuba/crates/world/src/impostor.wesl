// A tree's impostor: a quad facing the camera, showing the tree as its full version looks from there, blended from the
// three baked views nearest the camera's direction (impostor.rs). Each vertex places one tree, its corner in the first
// texture coordinates and its yaw and scale in the second, so a mesh can hold many trees.
import bevy_pbr::render::{
    forward_io::{Vertex, FragmentOutput, decompress_vertex},
    mesh_bindings::mesh,
    mesh_functions,
    mesh_view_bindings::view,
    pbr_functions,
    pbr_types,
    view_transformations::position_world_to_clip,
};

struct ImpostorParams {
    // Frames along each atlas side, pixels along each frame side, the bounding sphere's radius, unused.
    grid: vec4<f32>,
    // The bounding sphere's centre, in the tree's own frame (the quads hold it already).
    centre: vec4<f32>,
    push_haze: vec4<f32>,
    haze_colour: vec4<f32>,
}
@group(constants::MATERIAL_BIND_GROUP) @binding(100) var albedo_texture: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(101) var albedo_sampler: sampler;
@group(constants::MATERIAL_BIND_GROUP) @binding(102) var normal_texture: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(103) var normal_sampler: sampler;
@group(constants::MATERIAL_BIND_GROUP) @binding(104) var<uniform> params: ImpostorParams;

struct Out {
    @builtin(position) position: vec4<f32>,
    @location(0) world_position: vec4<f32>,
    // The fragment on the quad, and the camera, in the tree's frame around its sphere's centre, in metres.
    @location(1) local: vec3<f32>,
    @location(2) @interpolate(flat) eye: vec3<f32>,
    // Where the camera's direction falls on the grid of views, from 0 to grid - 1 on each axis.
    @location(3) @interpolate(flat) cell: vec2<f32>,
    // The tree's axes in the world, unit length.
    @location(4) @interpolate(flat) axis_x: vec3<f32>,
    @location(5) @interpolate(flat) axis_z: vec3<f32>,
    @location(6) @interpolate(flat) instance_index: u32,
    @if(VISIBILITY_RANGE_DITHER)
    @location(7) @interpolate(flat) visibility_range_dither: i32,
}

// The direction a view of grid point `cell` looks from, y up, as the bake (`direction`) has it.
fn direction(cell: vec2<f32>) -> vec3<f32> {
    let o = cell / (params.grid.x - 1.0) * 2.0 - 1.0;
    let a = (o.x + o.y) * 0.5;
    let b = (o.x - o.y) * 0.5;
    return normalize(vec3<f32>(a, 1.0 - abs(a) - abs(b), b));
}

// A view's right and up, as the bake (`basis`) has them.
fn basis(d: vec3<f32>) -> mat2x3<f32> {
    let hint = select(vec3<f32>(0.0, 1.0, 0.0), vec3<f32>(0.0, 0.0, 1.0), abs(d.y) > 0.999);
    let right = normalize(cross(hint, d));
    return mat2x3<f32>(right, cross(d, right));
}

@vertex
fn vertex(vertex_in: Vertex) -> Out {
    let vertex = decompress_vertex(vertex_in, vertex_in.instance_index);
    let world_from_local = mesh_functions::get_world_from_local(vertex_in.instance_index);
    // The vertex is the sphere's centre moved to a corner of the box around it (impostor.rs `quads`).
    let side = select(0.0, vertex.uv.x * 2.0 - 1.0, vertex.uv.x == vertex.uv.y);
    let middle = vertex.position - vec3<f32>(side * params.grid.z * vertex.uv_b.y);
    let centre = (world_from_local * vec4<f32>(middle, 1.0)).xyz;
    let yaw = vertex.uv_b.x;
    let turn = mat3x3<f32>(vec3<f32>(cos(yaw), 0.0, -sin(yaw)), vec3<f32>(0.0, 1.0, 0.0), vec3<f32>(sin(yaw), 0.0, cos(yaw)));
    let axes = mat3x3<f32>(world_from_local[0].xyz, world_from_local[1].xyz, world_from_local[2].xyz) * turn * vertex.uv_b.y;
    let scale = length(axes[0]);
    let radius = params.grid.z * scale;
    let towards = view.world_position - centre;
    let d = normalize(towards);
    var right = cross(vec3<f32>(0.0, 1.0, 0.0), d);
    right = select(normalize(right), vec3<f32>(1.0, 0.0, 0.0), dot(right, right) < 1e-8);
    let up = cross(d, right);
    let corner = vertex.uv * 2.0 - 1.0;
    let world = centre + (right * corner.x + up * corner.y) * radius;
    var out: Out;
    out.world_position = vec4<f32>(world, 1.0);
    out.position = position_world_to_clip(world);
    let local_from_world = transpose(axes) * (1.0 / (scale * scale));
    out.local = local_from_world * (world - centre);
    out.eye = local_from_world * towards;
    // Seen from below the horizon, a tree shows its level views.
    var seen = normalize(out.eye);
    seen.y = max(seen.y, 0.0);
    seen /= abs(seen.x) + abs(seen.y) + abs(seen.z);
    out.cell = (vec2<f32>(seen.x + seen.z, seen.x - seen.z) * 0.5 + 0.5) * (params.grid.x - 1.0);
    out.axis_x = axes[0] / scale;
    out.axis_z = axes[2] / scale;
    out.instance_index = vertex_in.instance_index;
    @if(VISIBILITY_RANGE_DITHER)
    out.visibility_range_dither =
        mesh_functions::get_visibility_range_dither_level(vertex_in.instance_index, world_from_local[3]);
    return out;
}

// Where the view of grid point `cell` is hit by the ray from the eye through `local`: the atlas point, its gradients,
// whether it falls on the view's frame, and the hit point on the view's plane.
struct Place {
    uv: vec2<f32>,
    gx: vec2<f32>,
    gy: vec2<f32>,
    on: bool,
    point: vec3<f32>,
    d: vec3<f32>,
}

fn place(cell: vec2<f32>, local: vec3<f32>, eye: vec3<f32>) -> Place {
    let d = direction(cell);
    let b = basis(d);
    let ray = local - eye;
    var p: Place;
    p.d = d;
    p.point = eye + ray * (-dot(eye, d) / dot(ray, d));
    let inside = vec2<f32>(dot(p.point, b[0]), -dot(p.point, b[1])) / params.grid.z * 0.5 + 0.5;
    let margin = 0.5 / params.grid.y;
    p.uv = (cell + clamp(inside, vec2<f32>(margin), vec2<f32>(1.0 - margin))) / params.grid.x;
    p.gx = dpdx(inside) / params.grid.x;
    p.gy = dpdy(inside) / params.grid.x;
    p.on = all(inside >= vec2<f32>(0.0)) && all(inside <= vec2<f32>(1.0));
    return p;
}

// The view's albedo there, with no cover off its frame.
fn albedo_at(p: Place) -> vec4<f32> {
    let albedo = textureSampleGrad(albedo_texture, albedo_sampler, p.uv, p.gx, p.gy);
    return select(vec4<f32>(albedo.rgb, 0.0), albedo, p.on);
}

// The view's normal there, depth in alpha.
fn normal_at(p: Place) -> vec4<f32> {
    return textureSampleGrad(normal_texture, normal_sampler, p.uv, p.gx, p.gy);
}

@fragment
fn fragment(in: Out) -> FragmentOutput {
    @if(VISIBILITY_RANGE_DITHER)
    pbr_functions::visibility_range_dither(in.position, in.visibility_range_dither);
    let last = params.grid.x - 1.0;
    let cell = min(floor(in.cell), vec2<f32>(last - 1.0));
    let f = in.cell - cell;
    // The grid square's triangle the direction falls in, and its corners' weights.
    let upper = f.x + f.y > 1.0;
    let first = select(cell, cell + vec2<f32>(1.0, 1.0), upper);
    let weights = select(vec3<f32>(1.0 - f.x - f.y, f.x, f.y), vec3<f32>(f.x + f.y - 1.0, 1.0 - f.y, 1.0 - f.x), upper);
    let pa = place(first, in.local, in.eye);
    let pb = place(cell + vec2<f32>(1.0, 0.0), in.local, in.eye);
    let pc = place(cell + vec2<f32>(0.0, 1.0), in.local, in.eye);
    // Only the albedo first: most of a quad shows no tree, and those fragments read nothing more.
    let aa = albedo_at(pa);
    let ab = albedo_at(pb);
    let ac = albedo_at(pc);
    let coverage = aa.a * weights.x + ab.a * weights.y + ac.a * weights.z;
    if coverage < 0.5 {
        discard;
    }
    let albedo = (aa.rgb * weights.x + ab.rgb * weights.y + ac.rgb * weights.z);
    let na = normal_at(pa);
    let nb = normal_at(pb);
    let nc = normal_at(pc);
    let n = (na.xyz * weights.x + nb.xyz * weights.y + nc.xyz * weights.z) * 2.0 - 1.0;
    let radius = params.grid.z;
    let sa = pa.point + pa.d * ((na.a * 2.0 - 1.0) * radius);
    let sb = pb.point + pb.d * ((nb.a * 2.0 - 1.0) * radius);
    let sc = pc.point + pc.d * ((nc.a * 2.0 - 1.0) * radius);
    let surface_local = sa * weights.x + sb * weights.y + sc * weights.z;
    let axis_y = cross(in.axis_z, in.axis_x);
    let to_world = mat3x3<f32>(in.axis_x, axis_y, in.axis_z);
    let scale = length(in.world_position.xyz - view.world_position) / max(length(in.local - in.eye), 1e-4);
    let world_position = vec4<f32>(view.world_position + to_world * (surface_local - in.eye) * scale, 1.0);

    var surface = pbr_types::pbr_input_new();
    surface.flags = mesh[in.instance_index].flags;
    surface.is_orthographic = view.clip_from_view[3].w == 1.0;
    surface.frag_coord = in.position;
    surface.world_position = world_position;
    surface.world_normal = normalize(to_world * n);
    surface.N = surface.world_normal;
    surface.V = pbr_functions::calculate_view(world_position, surface.is_orthographic);
    surface.material.perceptual_roughness = 1.0;
    surface.material.metallic = 0.0;
    surface.material.reflectance = vec3<f32>(0.0);
    let depth = max(-(view.view_from_world * world_position).z, 0.0);
    let haze = 1.0 - exp(-max(depth - params.push_haze.z, 0.0) / params.push_haze.w);
    surface.material.base_color = vec4<f32>(albedo * (1.0 - haze), 1.0);
    surface.material.emissive = vec4<f32>(params.haze_colour.xyz * haze, 1.0);
    var out: FragmentOutput;
    out.color = pbr_functions::main_pass_post_lighting_processing(surface, pbr_functions::apply_pbr_lighting(surface));
    @if(FORWARD_MOTION)
    out.motion_vector = bevy_pbr::render::motion_vectors::calculate(world_position, world_position);
    return out;
}
