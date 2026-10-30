//! Shared rendering commands for rigid meshes and 3D shadow views.

use std::ops::Range;

use bevy::core_pipeline::core_3d::{AlphaMask3d, Opaque3d};
use bevy::core_pipeline::prepass::{AlphaMask3dPrepass, MotionVectorPrepass, Opaque3dPrepass};

use bevy::ecs::query::{Has, QueryEntityError, QueryState};
use bevy::ecs::system::lifetimeless::SRes;
use bevy::ecs::system::{ReadOnlySystemParam, SystemParamItem, SystemState};
use bevy::light::{Cascades, SimulationLightSystems};
use bevy::pbr::{
    DrawDepthOnlyPrepass, DrawMaterial, DrawMesh, DrawPrepass, MeshBindGroups, MeshMorphBindGroupKey, MorphIndices,
    PreprocessBindGroups, PreprocessPipeline, PreprocessPipelines, RenderMeshInstances, SetMaterialBindGroup,
    SetMeshBindGroup, SetMeshViewBindGroup, SetMeshViewBindingArrayBindGroup, SetPrepassEmptyMaterialBindGroup,
    SetPrepassViewBindGroup, SetPrepassViewEmptyBindGroup, Shadow, SkinUniforms,
};
use bevy::platform::collections::{HashMap, HashSet};
use bevy::prelude::*;
use bevy::render::batching::gpu_preprocessing::{GpuPreprocessingMode, GpuPreprocessingSupport};
use bevy::render::mesh::allocator::{MeshAllocator, MeshSlabs, allocate_and_free_meshes};
use bevy::render::mesh::{MeshMetadataFallbackBuffer, RenderMesh, RenderMeshBufferInfo};
use bevy::render::render_asset::{ExtractedAssets, RenderAssets, prepare_assets};
use bevy::render::render_phase::{
    Draw, DrawError, DrawFunctions, PhaseItem, PhaseItemExtraIndex, RenderCommand, RenderCommandResult,
    SetItemPipeline, TrackedRenderPass,
};
use bevy::render::render_resource::{Buffer, IndexFormat, PipelineCache};
use bevy::render::sync_world::{MainEntity, MainEntityHashSet};
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
                    // Extraction has updated skin allocations and morph weights before this render schedule starts.
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

/// The commands before each rigid mesh's binding and draw; Bevy's own are `(.., SetMeshBindGroup<2>, DrawMesh)`.
type MaterialCommands =
    (SetItemPipeline, SetMeshViewBindGroup<0>, SetMeshViewBindingArrayBindGroup<1>, SetMaterialBindGroup<3>);
type PrepassCommands =
    (SetItemPipeline, SetPrepassViewBindGroup<0>, SetPrepassViewEmptyBindGroup<1>, SetMaterialBindGroup<3>);
type DepthCommands =
    (SetItemPipeline, SetPrepassViewBindGroup<0>, SetPrepassViewEmptyBindGroup<1>, SetPrepassEmptyMaterialBindGroup<3>);

fn register(world: &mut World) {
    let command = FastDraw::<Opaque3d, MaterialCommands>::new(world);
    world.resource::<DrawFunctions<Opaque3d>>().write().add_with::<DrawMaterial, _>(command);
    let command = FastDraw::<AlphaMask3d, MaterialCommands>::new(world);
    world.resource::<DrawFunctions<AlphaMask3d>>().write().add_with::<DrawMaterial, _>(command);
    let command = FastDraw::<Opaque3dPrepass, PrepassCommands>::new(world);
    world.resource::<DrawFunctions<Opaque3dPrepass>>().write().add_with::<DrawPrepass, _>(command);
    let command = FastDraw::<AlphaMask3dPrepass, PrepassCommands>::new(world);
    world.resource::<DrawFunctions<AlphaMask3dPrepass>>().write().add_with::<DrawPrepass, _>(command);
    let command = FastDraw::<Opaque3dPrepass, DepthCommands>::new(world);
    world.resource::<DrawFunctions<Opaque3dPrepass>>().write().add_with::<DrawDepthOnlyPrepass, _>(command);
    let command = FastDraw::<Shadow, PrepassCommands>::new(world);
    world.resource::<DrawFunctions<Shadow>>().write().add_with::<DrawPrepass, _>(command);
    let command = FastDraw::<Shadow, DepthCommands>::new(world);
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
    /// Entities whose current skin or morph weights require Bevy's own binding.
    deformed: MainEntityHashSet,
    /// Whether the noted draws can be used this update: when the shaders preparing each instance's data are loaded and
    /// draw directly, not indirectly. Bevy's own draw is used until then.
    direct: bool,
}

impl MeshDraws {
    /// Skin allocations and morph indices are updated during extraction. Refresh their union every render frame.
    fn note_deformed<'a>(&mut self, skins: impl IntoIterator<Item = &'a MainEntity>, morphs: &MorphIndices) {
        self.deformed.clear();
        self.deformed.extend(skins);
        match morphs {
            MorphIndices::Uniform { current, .. } => self.deformed.extend(current.keys()),
            MorphIndices::Storage { morph_weights_info, .. } => self.deformed.extend(morph_weights_info.keys()),
        }
    }

    #[inline]
    fn rigid_mesh_id(&self, instances: &RenderMeshInstances, entity: MainEntity) -> Option<AssetId<Mesh>> {
        let RenderMeshInstances::GpuBuilding(gpu_instances) = instances else { return None };
        let data = gpu_instances.get(&entity)?;
        if data.shared.lightmap_slab_index().is_some() || self.deformed.contains(&entity) {
            return None;
        }
        Some(data.shared.mesh_asset_id())
    }
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
    skins: Res<SkinUniforms>,
    morphs: Res<MorphIndices>,
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
    draws.note_deformed(skins.all_skins(), &morphs);
}

/// What every rigid mesh's draw reads. Bevy's draw state fetches each resource its commands might use for every item,
/// which in the browser costs as much as the draw itself, so the resources only a fallback needs are fetched when used.
type FastParam = (SRes<MeshDraws>, SRes<RenderMeshInstances>, SRes<MeshBindGroups>);
/// Read only for a mesh not yet noted, or noted without a metadata slab.
type UnnotedParam = (SRes<MeshAllocator>, SRes<MeshMetadataFallbackBuffer>);
type BindParam<P> = <SetMeshBindGroup<2> as RenderCommand<P>>::Param;
type DrawParam<P> = <DrawMesh as RenderCommand<P>>::Param;

/// Runs the commands `C`, then binds a rigid GPU-built mesh with Bevy's metadata slab and dynamic offset, without
/// querying device limits for every draw, and draws it directly from its noted draw. Anything requiring skin, morph or
/// lightmap data uses Bevy's own binding; a mesh drawn indirectly or not yet noted uses Bevy's own draw. It is the
/// draw state of `(C, SetMeshBindGroup<2>, DrawMesh)` with the fallbacks' resources fetched only when they are used.
struct FastDraw<P: PhaseItem, C: RenderCommand<P>> {
    state: SystemState<(C::Param, FastParam)>,
    view: QueryState<(C::ViewQuery, Has<MotionVectorPrepass>, Has<PreprocessBindGroups>)>,
    entity: QueryState<C::ItemQuery>,
    unnoted: SystemState<UnnotedParam>,
    bind: SystemState<BindParam<P>>,
    draw: SystemState<DrawParam<P>>,
}

impl<P: PhaseItem, C: RenderCommand<P>> FastDraw<P, C> {
    fn new(world: &mut World) -> Self {
        Self {
            state: SystemState::new(world),
            view: world.query(),
            entity: world.query(),
            unnoted: SystemState::new(world),
            bind: SystemState::new(world),
            draw: SystemState::new(world),
        }
    }
}

impl<P: PhaseItem, C: RenderCommand<P> + Send + Sync + 'static> Draw<P> for FastDraw<P, C>
where
    C::Param: ReadOnlySystemParam,
{
    fn prepare(&mut self, world: &World) {
        self.view.update_archetypes(world);
        self.entity.update_archetypes(world);
    }

    fn draw<'w>(
        &mut self,
        world: &'w World,
        pass: &mut TrackedRenderPass<'w>,
        view: Entity,
        item: &P,
    ) -> Result<(), DrawError> {
        let Self { state, view: views, entity, unnoted, bind, draw } = self;
        let (commands, fast) = state.get(world).expect("rigid mesh draw resources");
        let (view, motion, preprocessed) = match views.get_manual(world, view) {
            Ok(view) => view,
            Err(QueryEntityError::NotSpawned(_)) => return Err(DrawError::ViewEntityNotFound),
            Err(_) => return Err(DrawError::InvalidViewQuery),
        };
        let query = entity.get_manual(world, item.entity()).ok();
        // Bevy's binding and draw have no item query of their own; they see whether the item's whole query matched.
        let found = query.is_some().then_some(());
        let result = match C::render(item, view, query, commands, pass) {
            RenderCommandResult::Success => {
                let fallback = Fallback { world, found, motion, preprocessed, unnoted, bind, draw };
                draw_mesh(item, fast, fallback, pass)
            }
            result => result,
        };
        match result {
            RenderCommandResult::Success | RenderCommandResult::Skip => Ok(()),
            RenderCommandResult::Failure(reason) => Err(DrawError::RenderCommandFailure(reason)),
        }
    }
}

/// What a rigid mesh's draw needs to fetch Bevy's own binding and draw, when it uses them.
struct Fallback<'w, 's, P: PhaseItem> {
    world: &'w World,
    found: Option<()>,
    motion: bool,
    preprocessed: bool,
    unnoted: &'s mut SystemState<UnnotedParam>,
    bind: &'s mut SystemState<BindParam<P>>,
    draw: &'s mut SystemState<DrawParam<P>>,
}

impl<'w, P: PhaseItem> Fallback<'w, '_, P> {
    fn unnoted(&mut self) -> SystemParamItem<'w, '_, UnnotedParam> {
        self.unnoted.get(self.world).expect("mesh allocator")
    }

    fn draw(&mut self, item: &P, pass: &mut TrackedRenderPass<'w>) -> RenderCommandResult {
        DrawMesh::render(item, self.preprocessed, self.found, self.draw.get(self.world).expect("mesh draw"), pass)
    }

    fn bind_and_draw(mut self, item: &P, pass: &mut TrackedRenderPass<'w>) -> RenderCommandResult {
        let bind = self.bind.get(self.world).expect("mesh binding");
        match SetMeshBindGroup::<2>::render(item, self.motion, self.found, bind, pass) {
            RenderCommandResult::Success => self.draw(item, pass),
            result => result,
        }
    }
}

fn draw_mesh<'w, P: PhaseItem>(
    item: &P,
    (draws, instances, groups): SystemParamItem<'w, '_, FastParam>,
    mut fallback: Fallback<'w, '_, P>,
    pass: &mut TrackedRenderPass<'w>,
) -> RenderCommandResult {
    let entity = item.main_entity();
    let draws = draws.into_inner();
    // This is the same shared instance data returned by Bevy's queue-data lookup, without cloning render layers.
    let rigid = if let Some(id) = draws.rigid_mesh_id(&instances, entity) {
        let noted = draws.noted.ready.get(&id);
        let slabs = match noted {
            Some(mesh) => Some(mesh.slabs),
            None => fallback.unnoted().0.mesh_slabs(&id),
        };
        if slabs.is_some_and(|slabs| slabs.morph_target_slab_id.is_some()) {
            None
        } else {
            let slab = match slabs.and_then(|slabs| slabs.metadata_slab_id) {
                Some(slab) => slab,
                None => fallback.unnoted().1.slab_id,
            };
            Some((slab, noted))
        }
    } else {
        None
    };
    let Some((slab, noted)) = rigid else { return fallback.bind_and_draw(item, pass) };
    let phase = match groups.into_inner() {
        MeshBindGroups::CpuPreprocessing(phase) => Some(phase),
        MeshBindGroups::GpuPreprocessing(phases) => phases.get(&std::any::TypeId::of::<P>()),
    };
    if let Some(phase) = phase {
        let Some(group) = phase.get(slab, None, false, MeshMorphBindGroupKey::NoMorphTargets, fallback.motion) else {
            return RenderCommandResult::Failure("missing static mesh bind group");
        };
        match item.extra_index() {
            PhaseItemExtraIndex::DynamicOffset(offset) => pass.set_bind_group(2, group, &[offset]),
            _ => pass.set_bind_group(2, group, &[]),
        }
    }
    // Bevy's draw also waits for the shaders preparing each instance's data and the view's prepared data, as here.
    let direct = matches!(item.extra_index(), PhaseItemExtraIndex::None | PhaseItemExtraIndex::DynamicOffset(_));
    let Some(mesh) = noted.filter(|_| direct && draws.direct && fallback.preprocessed) else {
        return fallback.draw(item, pass);
    };
    pass.set_vertex_buffer(0, mesh.vertices.slice(..));
    pass.set_index_buffer(mesh.indices.slice(..), mesh.index_format);
    pass.draw_indexed(mesh.index_range.clone(), mesh.first_vertex, item.batch_range().clone());
    RenderCommandResult::Success
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
    fn rigid_eligibility_tracks_current_skin_morph_lightmap_and_instances() {
        use bevy::pbr::{MorphIndex, RenderMeshInstanceGpu, RenderMeshInstanceGpuFlatBlob, RenderMeshInstancesGpu};
        use bevy::render::sync_world::MainEntityHashMap;

        let entities = [1, 2, 3].map(|n| MainEntity::from(Entity::from_raw_u32(n).unwrap()));
        let [rigid, skin, morph] = entities;
        let mesh = AssetId::<Mesh>::from(bevy::asset::uuid::Uuid::from_u128(7));
        let replacement = AssetId::<Mesh>::from(bevy::asset::uuid::Uuid::from_u128(8));
        let mut gpu = RenderMeshInstancesGpu::default();
        for entity in entities {
            let instance = RenderMeshInstanceGpu {
                shared: default(),
                gpu_specific: RenderMeshInstanceGpuFlatBlob::default(),
                render_layers: None,
            };
            instance.shared.set_mesh_asset_id(mesh);
            instance.shared.set_lightmap_slab_index(None);
            gpu.insert(entity, instance);
        }
        let mut instances = RenderMeshInstances::GpuBuilding(gpu);
        let mut draws = MeshDraws::default();
        let mut morphs =
            MorphIndices::Uniform { current: MainEntityHashMap::default(), prev: MainEntityHashMap::default() };
        let MorphIndices::Uniform { current, .. } = &mut morphs else { unreachable!() };
        current.insert(morph, MorphIndex { index: 0 });
        draws.note_deformed([&skin], &morphs);
        assert_eq!(draws.rigid_mesh_id(&instances, rigid), Some(mesh));
        assert_eq!(draws.rigid_mesh_id(&instances, skin), None);
        assert_eq!(draws.rigid_mesh_id(&instances, morph), None);

        // The next frame makes both deformed meshes rigid, and removes the former rigid instance.
        let MorphIndices::Uniform { current, .. } = &mut morphs else { unreachable!() };
        let old = current.remove(&morph).unwrap();
        let MorphIndices::Uniform { prev, .. } = &mut morphs else { unreachable!() };
        prev.insert(morph, old);
        draws.note_deformed([], &morphs);
        let RenderMeshInstances::GpuBuilding(gpu) = &mut instances else { unreachable!() };
        gpu.remove(&rigid);
        gpu.get(&skin).unwrap().shared.set_lightmap_slab_index(Some(0u32.into()));
        gpu.get(&morph).unwrap().shared.set_mesh_asset_id(replacement);
        assert_eq!(draws.rigid_mesh_id(&instances, rigid), None);
        assert_eq!(draws.rigid_mesh_id(&instances, skin), None);
        assert_eq!(draws.rigid_mesh_id(&instances, morph), Some(replacement));

        // An entity may become skinned or morphed again in a later frame.
        let MorphIndices::Uniform { current, .. } = &mut morphs else { unreachable!() };
        current.insert(skin, MorphIndex { index: 0 });
        draws.note_deformed([&morph], &morphs);
        let RenderMeshInstances::GpuBuilding(gpu) = &mut instances else { unreachable!() };
        gpu.get(&skin).unwrap().shared.set_lightmap_slab_index(None);
        assert_eq!(draws.rigid_mesh_id(&instances, skin), None);
        assert_eq!(draws.rigid_mesh_id(&instances, morph), None);

        // Switching to storage morphs also drops entries from the previous frame.
        let storage = MorphIndices::Storage {
            morph_weights_info: default(),
            gpu_descriptor_indices: default(),
            gpu_descriptor_free_list: vec![],
        };
        draws.note_deformed([], &storage);
        assert_eq!(draws.rigid_mesh_id(&instances, skin), Some(mesh));
        assert_eq!(draws.rigid_mesh_id(&instances, morph), Some(replacement));

        let cpu = RenderMeshInstances::CpuBuilding(default());
        assert_eq!(draws.rigid_mesh_id(&cpu, morph), None);
    }

    #[test]
    fn rigid_draws_fetch_fallback_resources_only_when_used() {
        let mut world = World::new();
        // Each draw state must build without conflicting access in every phase it is registered for.
        let _ = FastDraw::<Opaque3d, MaterialCommands>::new(&mut world);
        let _ = FastDraw::<AlphaMask3dPrepass, PrepassCommands>::new(&mut world);
        let draw = FastDraw::<Shadow, DepthCommands>::new(&mut world);
        let (draws, instances, groups) = draw.state.param_state().1;
        let read = [draws, instances, groups];
        // Resources read only by Bevy's own binding and draw, or for a mesh not yet noted, are not fetched per item.
        let fallback_only = [
            world.component_id::<MeshAllocator>(),
            world.component_id::<SkinUniforms>(),
            world.component_id::<MorphIndices>(),
            world.component_id::<MeshMetadataFallbackBuffer>(),
            world.component_id::<RenderAssets<RenderMesh>>(),
            world.component_id::<bevy::pbr::RenderLightmaps>(),
            world.component_id::<bevy::render::renderer::RenderDevice>(),
        ];
        assert!(fallback_only.iter().all(|id| id.is_some_and(|id| !read.contains(&id))));
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
