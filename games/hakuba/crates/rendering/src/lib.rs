//! Shared rendering commands for rigid meshes and 3D shadow views.

use std::ops::Range;

use bevy::core_pipeline::core_3d::{AlphaMask3d, Opaque3d};
use bevy::core_pipeline::prepass::{AlphaMask3dPrepass, MotionVectorPrepass, Opaque3dPrepass};
use bevy::ecs::query::Has;
use bevy::ecs::system::SystemParamItem;
use bevy::ecs::system::lifetimeless::SRes;
use bevy::light::{Cascades, SimulationLightSystems};
use bevy::pbr::{
    DrawDepthOnlyPrepass, DrawMaterial, DrawMesh, DrawPrepass, MeshBindGroups, MeshMorphBindGroupKey, MorphIndices,
    PreprocessBindGroups, PreprocessPipeline, PreprocessPipelines, RenderMeshInstances, SetMaterialBindGroup,
    SetMeshBindGroup, SetMeshViewBindGroup, SetMeshViewBindingArrayBindGroup, SetPrepassEmptyMaterialBindGroup,
    SetPrepassViewBindGroup, SetPrepassViewEmptyBindGroup, Shadow,
};
use bevy::platform::collections::{HashMap, HashSet};
use bevy::prelude::*;
use bevy::render::batching::gpu_preprocessing::{GpuPreprocessingMode, GpuPreprocessingSupport};
use bevy::render::mesh::allocator::{MeshAllocator, MeshSlabs, allocate_and_free_meshes};
use bevy::render::mesh::{RenderMesh, RenderMeshBufferInfo};
use bevy::render::render_asset::{ExtractedAssets, RenderAssets, prepare_assets};
use bevy::render::render_phase::{
    DrawFunctions, PhaseItem, PhaseItemExtraIndex, RenderCommand, RenderCommandResult, RenderCommandState,
    SetItemPipeline, TrackedRenderPass,
};
use bevy::render::render_resource::{Buffer, IndexFormat, PipelineCache};
use bevy::render::{Render, RenderApp, RenderStartup, RenderSystems};

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
            render_app.init_resource::<MeshDraws>().add_systems(RenderStartup, register).add_systems(
                Render,
                (
                    forget_mesh_draws
                        .in_set(RenderSystems::PrepareAssets)
                        .after(allocate_and_free_meshes)
                        .before(prepare_assets::<RenderMesh>),
                    note_mesh_draws.in_set(RenderSystems::PrepareResources).after(prepare_assets::<RenderMesh>),
                ),
            );
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

type FastMaterial =
    (SetItemPipeline, SetMeshViewBindGroup<0>, SetMeshViewBindingArrayBindGroup<1>, SetMaterialBindGroup<3>, FastMesh);
type FastPrepass =
    (SetItemPipeline, SetPrepassViewBindGroup<0>, SetPrepassViewEmptyBindGroup<1>, SetMaterialBindGroup<3>, FastMesh);

type FastDepth = (
    SetItemPipeline,
    SetPrepassViewBindGroup<0>,
    SetPrepassViewEmptyBindGroup<1>,
    SetPrepassEmptyMaterialBindGroup<3>,
    FastMesh,
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

/// What a rigid, indexed mesh's draw needs, noted once instead of looked up in the mesh allocator by every draw: in the
/// browser those lookups cost more than the draw calls themselves.
struct MeshDraw {
    slabs: MeshSlabs,
    vertices: Buffer,
    first_vertex: i32,
    indices: Buffer,
    index_range: Range<u32>,
    index_format: IndexFormat,
}

impl MeshDraw {
    fn new(id: AssetId<Mesh>, mesh: &RenderMesh, allocator: &MeshAllocator) -> Option<Self> {
        let RenderMeshBufferInfo::Indexed { count, index_format } = mesh.buffer_info else { return None };
        let slabs = allocator.mesh_slabs(&id)?;
        let vertices = allocator.mesh_vertex_slice(&id)?;
        let indices = allocator.mesh_index_slice(&id)?;
        Some(Self {
            slabs,
            vertices: vertices.buffer.clone(),
            first_vertex: vertices.range.start as i32,
            indices: indices.buffer.clone(),
            index_range: indices.range.start..indices.range.start + count,
            index_format,
        })
    }
}

/// Each mesh's noted draw, and the meshes to note once they are prepared.
struct Noted<T> {
    ready: HashMap<AssetId<Mesh>, T>,
    pending: HashSet<AssetId<Mesh>>,
}

impl<T> Default for Noted<T> {
    fn default() -> Self {
        Self { ready: HashMap::default(), pending: HashSet::default() }
    }
}

impl<T> Noted<T> {
    /// Forgets removed meshes, and meshes that changed or whose buffer moved, which wait to be noted again.
    fn forget(
        &mut self,
        removed: impl IntoIterator<Item = AssetId<Mesh>>,
        changed: impl IntoIterator<Item = AssetId<Mesh>>,
    ) {
        for id in removed {
            self.ready.remove(&id);
            self.pending.remove(&id);
        }
        for id in changed {
            self.ready.remove(&id);
            self.pending.insert(id);
        }
    }

    /// Notes the waiting meshes that are prepared; `note` gives `None` for a mesh still preparing, and `Some(None)` for
    /// one that keeps Bevy's own draw.
    fn note(&mut self, mut note: impl FnMut(AssetId<Mesh>) -> Option<Option<T>>) {
        let Self { ready, pending } = self;
        pending.retain(|id| match note(*id) {
            None => true,
            Some(draw) => {
                if let Some(draw) = draw {
                    ready.insert(*id, draw);
                }
                false
            }
        });
    }
}

#[derive(Resource, Default)]
struct MeshDraws {
    noted: Noted<MeshDraw>,
    /// Whether the noted draws can be used this update: when the shaders preparing each instance's data are loaded and
    /// draw directly, not indirectly. Bevy's own draw is used until then.
    direct: bool,
}

/// Runs after the allocator has placed this update's meshes, and before their removals are cleared.
fn forget_mesh_draws(
    mut draws: ResMut<MeshDraws>,
    extracted: Res<ExtractedAssets<RenderMesh>>,
    allocator: Res<MeshAllocator>,
) {
    let changed = extracted.extracted.iter().map(|(id, _)| *id).chain(allocator.meshes_displaced_by_slab_growth());
    draws.noted.forget(extracted.removed.iter().copied(), changed);
}

fn note_mesh_draws(
    mut draws: ResMut<MeshDraws>,
    meshes: Res<RenderAssets<RenderMesh>>,
    allocator: Res<MeshAllocator>,
    pipelines: Option<Res<PreprocessPipelines>>,
    support: Res<GpuPreprocessingSupport>,
    cache: Res<PipelineCache>,
) {
    let loaded =
        |pipeline: &PreprocessPipeline| pipeline.pipeline_id.is_some_and(|id| cache.get_compute_pipeline(id).is_some());
    draws.direct = support.max_supported_mode == GpuPreprocessingMode::PreprocessingOnly
        && pipelines.is_some_and(|pipelines| {
            loaded(&pipelines.direct_preprocess) && loaded(&pipelines.gpu_frustum_culling_preprocess)
        });
    draws.noted.note(|id| meshes.get(id).map(|mesh| MeshDraw::new(id, mesh, &allocator)));
}

/// Binds a rigid GPU-built mesh with Bevy's metadata slab and dynamic offset, without querying device limits for every
/// draw, and draws it directly from its noted draw. Anything requiring skin, morph or lightmap data uses Bevy's own
/// binding; a mesh drawn indirectly or not yet noted uses Bevy's own draw.
struct FastMesh;
impl<P: PhaseItem> RenderCommand<P> for FastMesh {
    type Param =
        (<SetMeshBindGroup<2> as RenderCommand<P>>::Param, <DrawMesh as RenderCommand<P>>::Param, SRes<MeshDraws>);
    type ViewQuery = (Has<MotionVectorPrepass>, Has<PreprocessBindGroups>);
    type ItemQuery = ();

    fn render<'w>(
        item: &P,
        (motion, preprocessed): (bool, bool),
        query: Option<()>,
        (bind, draw, draws): SystemParamItem<'w, '_, Self::Param>,
        pass: &mut TrackedRenderPass<'w>,
    ) -> RenderCommandResult {
        let entity = item.main_entity();
        let draws = draws.into_inner();
        let rigid = {
            let (_, _, instances, skins, morphs, allocator, _, fallback) = &bind;
            // This is the same shared instance data returned by Bevy's queue-data lookup, without cloning render layers.
            if let RenderMeshInstances::GpuBuilding(gpu_instances) = &**instances
                && let Some(data) = gpu_instances.get(&entity)
                && data.shared.lightmap_slab_index().is_none()
                && skins.skin_byte_offset(entity).is_none()
                && !match &**morphs {
                    MorphIndices::Uniform { current, .. } => current.contains_key(&entity),
                    MorphIndices::Storage { morph_weights_info, .. } => morph_weights_info.contains_key(&entity),
                }
            {
                let id = data.shared.mesh_asset_id();
                let noted = draws.noted.ready.get(&id);
                let slabs = noted.map(|mesh| mesh.slabs).or_else(|| allocator.mesh_slabs(&id));
                if slabs.is_some_and(|slabs| slabs.morph_target_slab_id.is_some()) {
                    None
                } else {
                    Some((slabs.and_then(|slabs| slabs.metadata_slab_id).unwrap_or(fallback.slab_id), noted))
                }
            } else {
                None
            }
        };
        let Some((slab, noted)) = rigid else {
            return match SetMeshBindGroup::<2>::render(item, motion, query, bind, pass) {
                RenderCommandResult::Success => DrawMesh::render(item, preprocessed, query, draw, pass),
                result => result,
            };
        };
        let (_, groups, _, _, _, _, _, _) = bind;
        let phase = match groups.into_inner() {
            MeshBindGroups::CpuPreprocessing(phase) => Some(phase),
            MeshBindGroups::GpuPreprocessing(phases) => phases.get(&std::any::TypeId::of::<P>()),
        };
        if let Some(phase) = phase {
            let Some(group) = phase.get(slab, None, false, MeshMorphBindGroupKey::NoMorphTargets, motion) else {
                return RenderCommandResult::Failure("missing static mesh bind group");
            };
            match item.extra_index() {
                PhaseItemExtraIndex::DynamicOffset(offset) => pass.set_bind_group(2, group, &[offset]),
                _ => pass.set_bind_group(2, group, &[]),
            }
        }
        // Bevy's draw also waits for the shaders preparing each instance's data and the view's prepared data, as here.
        let direct = matches!(item.extra_index(), PhaseItemExtraIndex::None | PhaseItemExtraIndex::DynamicOffset(_));
        let Some(mesh) = noted.filter(|_| direct && draws.direct && preprocessed) else {
            return DrawMesh::render(item, preprocessed, query, draw, pass);
        };
        pass.set_vertex_buffer(0, mesh.vertices.slice(..));
        pass.set_index_buffer(mesh.indices.slice(..), mesh.index_format);
        pass.draw_indexed(mesh.index_range.clone(), mesh.first_vertex, item.batch_range().clone());
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
    fn noted_draws_follow_changed_and_removed_meshes() {
        let [a, b, c] = [1, 2, 3].map(|n| AssetId::<Mesh>::from(bevy::asset::uuid::Uuid::from_u128(n)));
        let mut noted = Noted::<u32>::default();
        noted.forget([], [a, b, c]);
        // `a` is prepared, `b` keeps Bevy's own draw, `c` is still preparing.
        noted.note(|id| match id {
            id if id == a => Some(Some(1)),
            id if id == b => Some(None),
            _ => None,
        });
        assert_eq!(noted.ready.get(&a), Some(&1));
        assert!(!noted.ready.contains_key(&b) && !noted.pending.contains(&b));
        assert!(noted.pending.contains(&c));
        // A changed or moved mesh is forgotten until noted again; a removed one is forgotten for good.
        noted.forget([c], [a]);
        assert!(noted.ready.is_empty());
        assert_eq!(noted.pending.iter().collect::<Vec<_>>(), [&a]);
        noted.note(|_| Some(Some(2)));
        assert_eq!(noted.ready.get(&a), Some(&2));
        assert!(noted.pending.is_empty());
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
