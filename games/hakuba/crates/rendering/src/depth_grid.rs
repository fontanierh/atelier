//! A coarse picture of how far the world camera sees, read back from the GPU for culling on the CPU: after the main
//! pass, a compute pass keeps the farthest depth in each of `GRID` cells of the main pass's depth, beside the camera
//! that drew it. Something whose nearest point lies beyond the farthest depth of every cell it covers is hidden behind
//! nearer things, as hierarchical depth culling finds.

use bevy::asset::{RenderAssetUsages, embedded_asset, load_embedded_asset};
use bevy::core_pipeline::core_3d::main_transparent_pass_3d;
use bevy::core_pipeline::prepass::ViewPrepassTextures;
use bevy::core_pipeline::schedule::{Core3d, Core3dSystems};
use bevy::prelude::*;
use bevy::render::gpu_readback::{Readback, ReadbackComplete};
use bevy::render::render_asset::RenderAssets;
use bevy::render::render_resource::binding_types::{storage_buffer_sized, texture_depth_2d};
use bevy::render::render_resource::{
    BindGroupEntries, BindGroupLayoutDescriptor, BindGroupLayoutEntries, CachedComputePipelineId,
    ComputePassDescriptor, ComputePipelineDescriptor, PipelineCache, ShaderStages,
};
use bevy::render::renderer::{RenderContext, RenderQueue, ViewQuery};
use bevy::render::storage::{GpuShaderBuffer, ShaderBuffer};
use bevy::render::view::ExtractedView;
use bevy::render::{Extract, ExtractSchedule, RenderApp, RenderStartup};

use crate::ForwardMotionMode;

/// The grid's cells across and down.
pub const GRID: UVec2 = UVec2::new(64, 36);
/// Ahead of the cells: the camera's clip-from-world matrix, its position and its rotation.
const HEADER: usize = 16 + 4 + 4;
const BYTES: u64 = ((HEADER + (GRID.x * GRID.y) as usize) * 4) as u64;

/// The last grid read back: each cell's farthest depth, reversed (1 at the near plane, 0 at infinity), and the camera
/// that saw it.
#[derive(Resource, Default)]
pub struct DepthGrid {
    pub clip_from_world: Mat4,
    pub eye: Vec3,
    pub rotation: Quat,
    pub cells: Vec<f32>,
    /// Counts the grids read back, so a reader can tell a new one.
    pub count: u32,
}

impl DepthGrid {
    /// The farthest depth in each cell, row by row from the top left.
    pub fn cell(&self, x: u32, y: u32) -> f32 {
        self.cells[(y * GRID.x + x) as usize]
    }
}

#[derive(Resource, Clone)]
struct GridBuffer(Handle<ShaderBuffer>);

#[derive(Resource)]
struct GridPipeline {
    layout: BindGroupLayoutDescriptor,
    pipeline: CachedComputePipelineId,
}

pub(super) fn build(app: &mut App) {
    embedded_asset!(app, "depth_grid.wesl");
    app.init_resource::<DepthGrid>().add_systems(Startup, request);
    if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
        render_app.add_systems(RenderStartup, (init_pipeline, install)).add_systems(ExtractSchedule, extract);
    }
}

fn request(mut commands: Commands, mut buffers: ResMut<Assets<ShaderBuffer>>) {
    let buffer = buffers.add(ShaderBuffer::with_size(BYTES, RenderAssetUsages::RENDER_WORLD));
    commands.insert_resource(GridBuffer(buffer.clone()));
    commands.spawn((Name::new("Depth grid readback"), Readback::buffer(buffer))).observe(read);
}

fn read(event: On<ReadbackComplete>, mut grid: ResMut<DepthGrid>) {
    let words: Vec<f32> = event.data.chunks_exact(4).map(|w| f32::from_ne_bytes([w[0], w[1], w[2], w[3]])).collect();
    if words.len() < HEADER {
        return;
    }
    let grid = &mut *grid;
    grid.clip_from_world = Mat4::from_cols_slice(&words[..16]);
    grid.eye = Vec3::from_slice(&words[16..19]);
    grid.rotation = Quat::from_slice(&words[20..24]);
    grid.cells.clear();
    grid.cells.extend_from_slice(&words[HEADER..]);
    grid.count = grid.count.wrapping_add(1);
}

fn extract(mut commands: Commands, buffer: Extract<Option<Res<GridBuffer>>>) {
    if let Some(buffer) = &*buffer
        && buffer.is_added()
    {
        commands.insert_resource((**buffer).clone());
    }
}

fn init_pipeline(mut commands: Commands, pipelines: Res<PipelineCache>, assets: Res<AssetServer>) {
    let layout = BindGroupLayoutDescriptor::new(
        "depth_grid_layout",
        &BindGroupLayoutEntries::sequential(
            ShaderStages::COMPUTE,
            (texture_depth_2d(), storage_buffer_sized(false, None)),
        ),
    );
    let pipeline = pipelines.queue_compute_pipeline(ComputePipelineDescriptor {
        label: Some("depth_grid".into()),
        layout: vec![layout.clone()],
        shader: load_embedded_asset!(assets.as_ref(), "depth_grid.wesl"),
        ..default()
    });
    commands.insert_resource(GridPipeline { layout, pipeline });
}

fn install(world: &mut World) {
    world.schedule_scope(Core3d, |_, schedule| {
        schedule.add_systems(
            shrink
                .in_set(Core3dSystems::MainPass)
                .after(super::forward_motion::draw_comparison)
                .before(main_transparent_pass_3d),
        );
    });
}

/// Shrinks the single-pass world camera's depth, as the main pass left it, into the grid.
fn shrink(
    view: ViewQuery<(&ExtractedView, &ViewPrepassTextures, &ForwardMotionMode)>,
    buffer: Option<Res<GridBuffer>>,
    buffers: Res<RenderAssets<GpuShaderBuffer>>,
    pipelines: Res<PipelineCache>,
    grid: Res<GridPipeline>,
    queue: Res<RenderQueue>,
    mut ctx: RenderContext,
) {
    let (view, prepass, mode) = view.into_inner();
    let (true, Some(depth), Some(buffer), Some(pipeline)) = (
        *mode == ForwardMotionMode::Single,
        &prepass.depth,
        buffer.and_then(|buffer| buffers.get(&buffer.0)),
        pipelines.get_compute_pipeline(grid.pipeline),
    ) else {
        return;
    };
    let clip_from_world =
        view.clip_from_world.unwrap_or_else(|| view.clip_from_view * view.world_from_view.to_matrix().inverse());
    let (_, rotation, eye) = view.world_from_view.to_scale_rotation_translation();
    let mut header = [0.0f32; HEADER];
    header[..16].copy_from_slice(&clip_from_world.to_cols_array());
    header[16..19].copy_from_slice(&eye.to_array());
    header[20..24].copy_from_slice(&rotation.to_array());
    let header: Vec<u8> = header.iter().flat_map(|w| w.to_ne_bytes()).collect();
    queue.write_buffer(&buffer.buffer, 0, &header);
    let group = ctx.render_device().create_bind_group(
        "depth_grid",
        &pipelines.get_bind_group_layout(&grid.layout),
        &BindGroupEntries::sequential((&depth.texture.default_view, buffer.buffer.as_entire_binding())),
    );
    let mut pass = ctx
        .command_encoder()
        .begin_compute_pass(&ComputePassDescriptor { label: Some("depth_grid"), timestamp_writes: None });
    pass.set_pipeline(pipeline);
    pass.set_bind_group(0, &group, &[]);
    pass.dispatch_workgroups(GRID.x, GRID.y, 1);
}
