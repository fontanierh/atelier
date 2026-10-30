//! Forward color/motion rendering and opt-in publication to TAA, with a comparison path for validation.

use bevy::asset::{embedded_asset, load_embedded_asset};
use bevy::camera::{MainPassResolutionOverride, Viewport};
use bevy::core_pipeline::FullscreenShader;
use bevy::core_pipeline::core_3d::{AlphaMask3d, Opaque3d, main_opaque_pass_3d, main_transparent_pass_3d};
use bevy::core_pipeline::prepass::{
    BackgroundMotionVectorsBindGroup, BackgroundMotionVectorsPipelineId, DeferredPrepass, MOTION_VECTOR_PREPASS_FORMAT,
    NormalPrepass, PreviousViewUniformOffset, ViewPrepassTextures,
};
use bevy::core_pipeline::schedule::{Core3d, Core3dSystems};
use bevy::core_pipeline::skybox::SkyboxPipelineId;
use bevy::ecs::schedule::ScheduleCleanupPolicy;
use bevy::pbr::{ContactShadows, ForwardMotion, ScreenSpaceTransmission};
use bevy::prelude::*;
use bevy::render::camera::ExtractedCamera;
use bevy::render::extract_component::{ExtractComponent, ExtractComponentPlugin};
use bevy::render::occlusion_culling::OcclusionCulling;
use bevy::render::render_phase::ViewBinnedRenderPhases;
use bevy::render::render_resource::{
    BindGroupEntries, BindGroupLayoutDescriptor, BindGroupLayoutEntries, CachedRenderPipelineId, ColorTargetState,
    ColorWrites, FragmentState, PipelineCache, RenderPassDescriptor, RenderPipelineDescriptor, ShaderStages, StoreOp,
    TextureDescriptor, TextureDimension, TextureSampleType, TextureUsages, binding_types::texture_2d,
};
use bevy::render::renderer::{RenderContext, RenderDevice, ViewQuery};
use bevy::render::texture::{ColorAttachment, TextureCache};
use bevy::render::view::{ExtractedView, ViewDepthStencilTexture, ViewTarget, ViewUniformOffset};
use bevy::render::{Render, RenderApp, RenderStartup, RenderSystems};

/// Explicit validation stages; normal cameras keep Bevy's original renderer.
#[derive(Component, Clone, Copy, Debug, PartialEq, Eq, ExtractComponent)]
#[extract_app(RenderApp)]
#[require(ForwardMotion)]
pub enum ForwardMotionMode {
    /// Keep the original prepass and displayed TAA, and write a separate comparison target.
    Compare,
    /// Keep the prepass for comparison, but publish main-pass motion and depth to TAA.
    Publish,
    /// Publish the main outputs and omit camera prepass geometry. Shadows are unchanged.
    Single,
}

/// Separate RG16Float main-pass motion target, also available for diagnostic readback.
#[derive(Component)]
pub struct ForwardMotionComparison {
    pub attachment: ColorAttachment,
    pub size: bevy::render::render_resource::Extent3d,
}

#[derive(Resource)]
struct MotionTransfer {
    layout: BindGroupLayoutDescriptor,
    pipeline: CachedRenderPipelineId,
}

pub(super) fn build(app: &mut App) {
    embedded_asset!(app, "forward_motion_transfer.wesl");
    app.add_plugins(ExtractComponentPlugin::<ForwardMotionMode>::default());
    if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
        render_app
            .add_systems(RenderStartup, (install_comparison_pass, init_motion_transfer))
            .add_systems(Render, prepare_comparison.in_set(RenderSystems::PrepareResources));
    }
}

fn install_comparison_pass(world: &mut World) {
    world.schedule_scope(Core3d, |world, schedule| {
        let removed = schedule
            .remove_systems_in_set(main_opaque_pass_3d, world, ScheduleCleanupPolicy::RemoveSystemsOnly)
            .expect("replace the registered opaque main pass");
        assert_eq!(removed, 1, "one opaque main pass must be registered");
        schedule.add_systems(
            (main_opaque_pass_3d.run_if(ordinary_view), draw_comparison)
                .in_set(Core3dSystems::MainPass)
                .before(main_transparent_pass_3d),
        );
    });
}

/// Keep the stock clear/background pass but omit all camera geometry commands once publication is ready.
pub(super) fn camera_prepass_elided(world: &World, view: Entity) -> bool {
    if world.get::<ForwardMotionMode>(view) != Some(&ForwardMotionMode::Single) {
        return false;
    }
    let transfer = world.resource::<MotionTransfer>();
    world.resource::<PipelineCache>().get_render_pipeline(transfer.pipeline).is_some()
}

fn init_motion_transfer(
    mut commands: Commands,
    pipelines: Res<PipelineCache>,
    fullscreen: Res<FullscreenShader>,
    assets: Res<AssetServer>,
) {
    let layout = BindGroupLayoutDescriptor::new(
        "forward_motion_transfer_layout",
        &BindGroupLayoutEntries::sequential(
            ShaderStages::FRAGMENT,
            (texture_2d(TextureSampleType::Float { filterable: false }),),
        ),
    );
    let pipeline = pipelines.queue_render_pipeline(RenderPipelineDescriptor {
        label: Some("forward_motion_transfer".into()),
        layout: vec![layout.clone()],
        vertex: fullscreen.to_vertex_state(),
        fragment: Some(FragmentState {
            shader: load_embedded_asset!(assets.as_ref(), "forward_motion_transfer.wesl"),
            targets: vec![Some(ColorTargetState {
                format: MOTION_VECTOR_PREPASS_FORMAT,
                blend: None,
                write_mask: ColorWrites::ALL,
            })],
            ..default()
        }),
        ..default()
    });
    commands.insert_resource(MotionTransfer { layout, pipeline });
}

fn ordinary_view(view: ViewQuery<Has<ForwardMotion>>) -> bool {
    !view.into_inner()
}

fn prepare_comparison(
    mut commands: Commands,
    device: Res<RenderDevice>,
    mut textures: ResMut<TextureCache>,
    views: Query<
        (
            Entity,
            &ExtractedCamera,
            &Msaa,
            Has<NormalPrepass>,
            Has<DeferredPrepass>,
            Has<SkyboxPipelineId>,
            Option<&MainPassResolutionOverride>,
            Has<ContactShadows>,
            Has<ScreenSpaceTransmission>,
            Has<OcclusionCulling>,
            Option<&ForwardMotionMode>,
        ),
        With<ForwardMotion>,
    >,
    stale: Query<Entity, (With<ForwardMotionComparison>, Without<ForwardMotion>)>,
) {
    for entity in &stale {
        commands.entity(entity).remove::<ForwardMotionComparison>();
    }
    for (entity, camera, msaa, normal, deferred, skybox, resolution, contact, transmission, occlusion, mode) in &views {
        assert!(
            *msaa == Msaa::Off && !normal && !deferred && !skybox && resolution.is_none(),
            "forward motion comparison supports the non-MSAA forward world camera with its mesh sky"
        );
        assert!(
            supported_temporal_features(mode, contact, transmission, occlusion),
            "forward motion does not support transmission, or single-pass early-depth consumers/occlusion culling"
        );
        let Some(size) = camera.physical_target_size else { continue };
        let size = bevy::render::render_resource::Extent3d { width: size.x, height: size.y, depth_or_array_layers: 1 };
        let texture = textures.get(
            &device,
            TextureDescriptor {
                label: Some("forward_motion_comparison"),
                size,
                mip_level_count: 1,
                sample_count: 1,
                dimension: TextureDimension::D2,
                format: MOTION_VECTOR_PREPASS_FORMAT,
                usage: TextureUsages::RENDER_ATTACHMENT | TextureUsages::TEXTURE_BINDING | TextureUsages::COPY_SRC,
                view_formats: &[],
            },
        );
        commands.entity(entity).insert(ForwardMotionComparison {
            attachment: ColorAttachment::new(texture, None, None, Some(LinearRgba::BLACK.into())),
            size,
        });
    }
}

fn supported_temporal_features(
    mode: Option<&ForwardMotionMode>,
    contact_shadows: bool,
    transmission: bool,
    occlusion_culling: bool,
) -> bool {
    !transmission && (mode != Some(&ForwardMotionMode::Single) || (!contact_shadows && !occlusion_culling))
}

fn draw_comparison(
    world: &World,
    view: ViewQuery<(
        &ExtractedCamera,
        &ExtractedView,
        &ViewTarget,
        &ViewDepthStencilTexture,
        &ForwardMotionComparison,
        &ViewUniformOffset,
        &PreviousViewUniformOffset,
        &ViewPrepassTextures,
        Option<&ForwardMotionMode>,
        Option<&MainPassResolutionOverride>,
        Option<&BackgroundMotionVectorsPipelineId>,
        Option<&BackgroundMotionVectorsBindGroup>,
    )>,
    opaque: Res<ViewBinnedRenderPhases<Opaque3d>>,
    masked: Res<ViewBinnedRenderPhases<AlphaMask3d>>,
    pipelines: Res<PipelineCache>,
    transfer: Res<MotionTransfer>,
    mut ctx: RenderContext,
) {
    let entity = view.entity();
    let (
        camera,
        extracted,
        color,
        depth,
        motion,
        view_offset,
        previous_offset,
        prepass,
        mode,
        resolution,
        background_pipeline,
        background_group,
    ) = view.into_inner();
    let (Some(opaque), Some(masked)) =
        (opaque.get(&extracted.retained_view_entity), masked.get(&extracted.retained_view_entity))
    else {
        return;
    };
    let viewport = Viewport::from_viewport_and_override(camera.viewport.as_ref(), resolution);
    {
        let attachments = [Some(color.get_color_attachment()), Some(motion.attachment.get_attachment())];
        let mut pass = ctx.begin_tracked_render_pass(RenderPassDescriptor {
            label: Some("main_opaque_pass_3d_forward_motion_comparison"),
            color_attachments: &attachments,
            depth_stencil_attachment: Some(depth.get_attachment(StoreOp::Store)),
            timestamp_writes: None,
            occlusion_query_set: None,
            multiview_mask: None,
        });
        if let Some(viewport) = &viewport {
            pass.set_camera_viewport(viewport);
        }
        if let Err(error) = opaque.render(&mut pass, world, entity) {
            error!("forward motion opaque draw failed: {error:?}");
        }
        if let Err(error) = masked.render(&mut pass, world, entity) {
            error!("forward motion masked draw failed: {error:?}");
        }
    }
    // Reuse Bevy's sky-depth-only motion draw for any pixels not covered by the mesh sky.
    if let (Some(id), Some(group)) = (background_pipeline, background_group)
        && let Some(pipeline) = pipelines.get_render_pipeline(id.0)
    {
        let attachments = [None, Some(motion.attachment.get_attachment()), None, None];
        let mut pass = ctx.begin_tracked_render_pass(RenderPassDescriptor {
            label: Some("forward_motion_comparison_background"),
            color_attachments: &attachments,
            depth_stencil_attachment: Some(depth.get_attachment(StoreOp::Store)),
            timestamp_writes: None,
            occlusion_query_set: None,
            multiview_mask: None,
        });
        if let Some(viewport) = &viewport {
            pass.set_camera_viewport(viewport);
        }
        pass.set_render_pipeline(pipeline);
        pass.set_bind_group(0, &group.0, &[view_offset.offset, previous_offset.offset]);
        pass.draw(0..3, 0..1);
    }
    if mode.is_some_and(|mode| *mode != ForwardMotionMode::Compare)
        && let Some(pipeline) = pipelines.get_render_pipeline(transfer.pipeline)
    {
        let (Some(destination_motion), Some(destination_depth)) = (&prepass.motion_vectors, &prepass.depth) else {
            return;
        };
        let group = ctx.render_device().create_bind_group(
            "forward_motion_transfer",
            &pipelines.get_bind_group_layout(&transfer.layout),
            &BindGroupEntries::single(&motion.attachment.texture.default_view),
        );
        {
            let attachments = [Some(destination_motion.get_attachment())];
            let mut pass = ctx.begin_tracked_render_pass(RenderPassDescriptor {
                label: Some("forward_motion_transfer"),
                color_attachments: &attachments,
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            if let Some(viewport) = &viewport {
                pass.set_camera_viewport(viewport);
            }
            pass.set_render_pipeline(pipeline);
            pass.set_bind_group(0, &group, &[]);
            pass.draw(0..3, 0..1);
        }
        ctx.command_encoder().copy_texture_to_texture(
            depth.texture().as_image_copy(),
            destination_depth.texture.texture.as_image_copy(),
            prepass.size,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::ecs::system::RunSystemOnce;

    #[test]
    fn single_pass_rejects_early_depth_consumers_and_transmission() {
        for mode in [ForwardMotionMode::Compare, ForwardMotionMode::Publish, ForwardMotionMode::Single] {
            assert!(supported_temporal_features(Some(&mode), false, false, false));
            assert!(!supported_temporal_features(Some(&mode), false, true, false));
            assert_eq!(supported_temporal_features(Some(&mode), true, false, false), mode != ForwardMotionMode::Single);
            assert_eq!(supported_temporal_features(Some(&mode), false, false, true), mode != ForwardMotionMode::Single);
        }
    }

    #[test]
    fn forward_motion_replaces_opaque_pass_and_initializes_core3d() {
        let mut world = World::new();
        world.add_schedule(Schedule::new(Core3d));
        world.schedule_scope(Core3d, |_, schedule| {
            schedule.add_systems((main_opaque_pass_3d, main_transparent_pass_3d).chain());
        });
        world.run_system_once(install_comparison_pass).unwrap();
        world.schedule_scope(Core3d, |world, schedule| {
            schedule.initialize(world).expect("comparison pass must fit the Core3d schedule");
        });
    }
}
