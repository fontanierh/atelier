//! Shared rendering commands for rigid meshes and 3D shadow views.

use bevy::core_pipeline::core_3d::{AlphaMask3d, Opaque3d};
use bevy::core_pipeline::prepass::{AlphaMask3dPrepass, MotionVectorPrepass, Opaque3dPrepass};
use bevy::ecs::query::Has;
use bevy::ecs::system::SystemParamItem;
use bevy::light::{Cascades, SimulationLightSystems};
use bevy::pbr::{
    DrawDepthOnlyPrepass, DrawMaterial, DrawMesh, DrawPrepass, MeshBindGroups, MeshMorphBindGroupKey, MorphIndices,
    RenderMeshInstances, SetMaterialBindGroup, SetMeshBindGroup, SetMeshViewBindGroup,
    SetMeshViewBindingArrayBindGroup, SetPrepassEmptyMaterialBindGroup, SetPrepassViewBindGroup,
    SetPrepassViewEmptyBindGroup, Shadow,
};
use bevy::prelude::*;
use bevy::render::render_phase::{
    DrawFunctions, PhaseItem, PhaseItemExtraIndex, RenderCommand, RenderCommandResult, RenderCommandState,
    SetItemPipeline, TrackedRenderPass,
};
use bevy::render::{RenderApp, RenderStartup};

pub struct RenderingPlugin;

impl Plugin for RenderingPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            PostUpdate,
            retain_3d_shadow_views
                .after(SimulationLightSystems::UpdateDirectionalLightCascades)
                .before(SimulationLightSystems::UpdateLightFrusta),
        );
        if let Some(render_app) = app.get_sub_app_mut(RenderApp) {
            render_app.add_systems(RenderStartup, register);
        }
    }
}

/// PBR prepares shadows only for 3D cameras; do not build shadow visibility for presentation-only views.
fn retain_3d_shadow_views(
    cameras: Query<(), With<Camera3d>>,
    mut lights: Query<&mut Cascades, With<DirectionalLight>>,
) {
    for mut cascades in &mut lights {
        cascades.cascades.retain(|view, _| cameras.contains(*view));
    }
}

type FastMaterial = (
    SetItemPipeline,
    SetMeshViewBindGroup<0>,
    SetMeshViewBindingArrayBindGroup<1>,
    FastBind,
    SetMaterialBindGroup<3>,
    DrawMesh,
);
type FastPrepass = (
    SetItemPipeline,
    SetPrepassViewBindGroup<0>,
    SetPrepassViewEmptyBindGroup<1>,
    FastBind,
    SetMaterialBindGroup<3>,
    DrawMesh,
);

type FastDepth = (
    SetItemPipeline,
    SetPrepassViewBindGroup<0>,
    SetPrepassViewEmptyBindGroup<1>,
    FastBind,
    SetPrepassEmptyMaterialBindGroup<3>,
    DrawMesh,
);

fn register(world: &mut World) {
    let command = RenderCommandState::<Opaque3d, FastMaterial>::new(world);
    world.resource::<DrawFunctions<Opaque3d>>().write().add_with::<DrawMaterial, _>(command);
    let command = RenderCommandState::<AlphaMask3d, FastMaterial>::new(world);
    world.resource::<DrawFunctions<AlphaMask3d>>().write().add_with::<DrawMaterial, _>(command);
    let command = RenderCommandState::<Opaque3dPrepass, FastPrepass>::new(world);
    world.resource::<DrawFunctions<Opaque3dPrepass>>().write().add_with::<DrawPrepass, _>(command);
    let command = RenderCommandState::<AlphaMask3dPrepass, FastPrepass>::new(world);
    world.resource::<DrawFunctions<AlphaMask3dPrepass>>().write().add_with::<DrawPrepass, _>(command);
    let command = RenderCommandState::<Opaque3dPrepass, FastDepth>::new(world);
    world.resource::<DrawFunctions<Opaque3dPrepass>>().write().add_with::<DrawDepthOnlyPrepass, _>(command);
    let command = RenderCommandState::<Shadow, FastPrepass>::new(world);
    world.resource::<DrawFunctions<Shadow>>().write().add_with::<DrawPrepass, _>(command);
    let command = RenderCommandState::<Shadow, FastDepth>::new(world);
    world.resource::<DrawFunctions<Shadow>>().write().add_with::<DrawDepthOnlyPrepass, _>(command);
}

/// Uses the stock mesh binding for anything requiring skin, morph or lightmap data. For rigid GPU-built meshes,
/// Bevy 0.20 uses the same metadata slab and dynamic offset without querying device limits for every draw.
struct FastBind;
impl<P: PhaseItem> RenderCommand<P> for FastBind {
    type Param = <SetMeshBindGroup<2> as RenderCommand<P>>::Param;
    type ViewQuery = Has<MotionVectorPrepass>;
    type ItemQuery = ();

    fn render<'w>(
        item: &P,
        motion: bool,
        query: Option<()>,
        param: SystemParamItem<'w, '_, Self::Param>,
        pass: &mut TrackedRenderPass<'w>,
    ) -> RenderCommandResult {
        let entity = item.main_entity();
        let eligibility = {
            let (_, _, instances, skins, morphs, allocator, _, fallback) = &param;
            // This is the same shared instance data returned by Bevy's queue-data lookup, without cloning render layers.
            if let RenderMeshInstances::GpuBuilding(gpu_instances) = &**instances
                && let Some(data) = gpu_instances.get(&entity)
            {
                let slabs = allocator.mesh_slabs(&data.shared.mesh_asset_id());
                let morphed = match &**morphs {
                    MorphIndices::Uniform { current, .. } => current.contains_key(&entity),
                    MorphIndices::Storage { morph_weights_info, .. } => morph_weights_info.contains_key(&entity),
                };
                if data.shared.lightmap_slab_index().is_some()
                    || skins.skin_byte_offset(entity).is_some()
                    || morphed
                    || slabs.as_ref().is_some_and(|slabs| slabs.morph_target_slab_id.is_some())
                {
                    None
                } else {
                    Some(slabs.and_then(|slabs| slabs.metadata_slab_id).unwrap_or(fallback.slab_id))
                }
            } else {
                None
            }
        };
        let Some(slab) = eligibility else {
            return SetMeshBindGroup::<2>::render(item, motion, query, param, pass);
        };
        let (_, groups, _, _, _, _, _, _) = param;
        let phase = match groups.into_inner() {
            MeshBindGroups::CpuPreprocessing(phase) => Some(phase),
            MeshBindGroups::GpuPreprocessing(phases) => phases.get(&std::any::TypeId::of::<P>()),
        };
        let Some(phase) = phase else { return RenderCommandResult::Success };
        let Some(group) = phase.get(slab, None, false, MeshMorphBindGroupKey::NoMorphTargets, motion) else {
            return RenderCommandResult::Failure("missing static mesh bind group");
        };
        match item.extra_index() {
            PhaseItemExtraIndex::DynamicOffset(offset) => pass.set_bind_group(2, group, &[offset]),
            _ => pass.set_bind_group(2, group, &[]),
        }
        RenderCommandResult::Success
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::asset::AssetApp;
    use bevy::ecs::system::RunSystemOnce;
    use bevy::light::cascade::Cascade;

    #[test]
    fn shadow_views_keep_3d_cascades_and_drop_2d() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        let camera_3d = app.world_mut().spawn(Camera3d::default()).id();
        let camera_2d = app.world_mut().spawn(Camera2d).id();
        let mut cascades = Cascades::default();
        let expected = Mat4::from_translation(Vec3::new(1.0, 2.0, 3.0));
        cascades.cascades.insert(camera_3d, vec![Cascade { clip_from_world: expected, ..default() }]);
        cascades.cascades.insert(camera_2d, vec![Cascade::default()]);
        let light = app.world_mut().spawn((DirectionalLight::default(), cascades)).id();
        app.world_mut().run_system_once(retain_3d_shadow_views).unwrap();
        let map = &app.world().get::<Cascades>(light).unwrap().cascades;
        assert_eq!(map.len(), 1);
        assert_eq!(map[&camera_3d][0].clip_from_world, expected);
        assert!(!map.contains_key(&camera_2d));
    }

    #[test]
    fn default_ui_schedule_accepts_shadow_filter_order() {
        let mut app = App::new();
        app.add_plugins(bevy::asset::AssetPlugin::default()).init_asset::<bevy::shader::Shader>();
        app.add_plugins(
            DefaultPlugins
                .build()
                .disable::<bevy::asset::AssetPlugin>()
                .disable::<bevy::render::RenderPlugin>()
                .disable::<bevy::winit::WinitPlugin>(),
        );
        app.add_plugins(RenderingPlugin);
        app.finish();
        app.cleanup();
        app.world_mut().schedule_scope(PostUpdate, |world, schedule| {
            schedule.initialize(world).expect("shadow filtering must fit the default schedule");
        });
    }
}
