"""Finite observations of nine original coastal component planners; no execution authority."""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import types
from atelier.build_v2.legacy_qualification import CallableObservation

class UnsupportedBrinecoveComponent(ValueError):
    """The declaration is outside the original nine component planners."""

@dataclass(frozen=True)
class BrinecoveComponent:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    verifier: CallableObservation

SCRIPT_ROLES = ('games/yorimichi/world/mesh_pieces.py',
 'games/yorimichi/world/random_stream.py',
 'games/yorimichi/world/region_mesh_parts.py',
 'games/yorimichi/world/region_mesh_set.py',
 'games/yorimichi/world/region_plan_files.py',
 'games/yorimichi/world/region_query.py',
 'games/yorimichi/world/regions/brinecove/__init__.py',
 'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
 'games/yorimichi/world/regions/brinecove/geom.py',
 'games/yorimichi/world/regions/brinecove/geometry_finish.py',
 'games/yorimichi/world/regions/brinecove/kit.py',
 'games/yorimichi/world/regions/brinecove/landmarks.py',
 'games/yorimichi/world/regions/brinecove/layout.py',
 'games/yorimichi/world/regions/brinecove/piece_inputs.py',
 'games/yorimichi/world/regions/brinecove/plan_component.py',
 'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
 'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
 'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
 'games/yorimichi/world/regions/brinecove/region.py',
 'games/yorimichi/world/regions/brinecove/rim_schema.py',
 'games/yorimichi/world/regions/brinecove/rocks.py',
 'games/yorimichi/world/regions/brinecove/surface_mapping.py',
 'games/yorimichi/world/yori.py',
 'platform/studio/atelier/__init__.py',
 'platform/studio/atelier/atomic_files.py',
 'platform/studio/atelier/export_manifest.py',
 'platform/studio/atelier/gltf.py',
 'platform/studio/atelier/mesh_cells.py',
 'platform/studio/atelier/mesh_collision.py',
 'platform/studio/atelier/mesh_ir.py',
 'platform/studio/atelier/mesh_materials.py',
 'platform/studio/atelier/mesh_partition.py',
 'platform/studio/atelier/model_export.py',
 'platform/studio/atelier/model_files.py',
 'platform/studio/atelier/paths.py')

COMPONENTS = {'Harbor': ('harbor',
            ('games/yorimichi/assets/brinecove/export-parameters/Harbor.json',
             'games/yorimichi/world/regions/brinecove/__init__.py',
             'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
             'games/yorimichi/world/regions/brinecove/geom.py',
             'games/yorimichi/world/regions/brinecove/kit.py',
             'games/yorimichi/world/regions/brinecove/landmarks.py',
             'games/yorimichi/world/regions/brinecove/layout.py',
             'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
             'games/yorimichi/world/regions/brinecove/procedural/covered.py',
             'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
             'games/yorimichi/world/regions/brinecove/procedural/harbor.py',
             'games/yorimichi/world/regions/brinecove/procedural/paving.py',
             'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py',
             'games/yorimichi/world/regions/brinecove/procedural/paving_material.py',
             'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
             'games/yorimichi/world/regions/brinecove/procedural/rowboat.py',
             'games/yorimichi/world/regions/brinecove/region.py',
             'games/yorimichi/world/regions/brinecove/rocks.py',
             'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
            ('games/yorimichi/world/regions/brinecove/__init__.py',
             'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
             'games/yorimichi/world/regions/brinecove/geom.py',
             'games/yorimichi/world/regions/brinecove/kit.py',
             'games/yorimichi/world/regions/brinecove/landmarks.py',
             'games/yorimichi/world/regions/brinecove/layout.py',
             'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
             'games/yorimichi/world/regions/brinecove/procedural/covered.py',
             'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
             'games/yorimichi/world/regions/brinecove/procedural/harbor.py',
             'games/yorimichi/world/regions/brinecove/procedural/paving.py',
             'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py',
             'games/yorimichi/world/regions/brinecove/procedural/paving_material.py',
             'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
             'games/yorimichi/world/regions/brinecove/procedural/rowboat.py',
             'games/yorimichi/world/regions/brinecove/region.py',
             'games/yorimichi/world/regions/brinecove/rocks.py',
             'games/yorimichi/world/regions/brinecove/surface_mapping.py')),
 'Landmarks': ('landmarks',
               ('games/yorimichi/assets/brinecove/export-parameters/Landmarks.json',
                'games/yorimichi/assets/brinecove/models/galleon-figurehead.glb',
                'games/yorimichi/assets/brinecove/models/galleon-hull.glb',
                'games/yorimichi/assets/brinecove/models/galleon-hull.provenance.json',
                'games/yorimichi/assets/brinecove/models/pirate-queen-statue.glb',
                'games/yorimichi/assets/brinecove/models/ships-wheel.glb',
                'games/yorimichi/world/regions/brinecove/__init__.py',
                'games/yorimichi/world/regions/brinecove/falls.py',
                'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                'games/yorimichi/world/regions/brinecove/geom.py',
                'games/yorimichi/world/regions/brinecove/ground_sampling.py',
                'games/yorimichi/world/regions/brinecove/kit.py',
                'games/yorimichi/world/regions/brinecove/landmarks.py',
                'games/yorimichi/world/regions/brinecove/layout.py',
                'games/yorimichi/world/regions/brinecove/paths.py',
                'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                'games/yorimichi/world/regions/brinecove/procedural/hero_presence.py',
                'games/yorimichi/world/regions/brinecove/procedural/landmarks.py',
                'games/yorimichi/world/regions/brinecove/procedural/lighthouse.py',
                'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                'games/yorimichi/world/regions/brinecove/procedural/rock_cluster.py',
                'games/yorimichi/world/regions/brinecove/procedural/statue.py',
                'games/yorimichi/world/regions/brinecove/region.py',
                'games/yorimichi/world/regions/brinecove/rocks.py',
                'games/yorimichi/world/regions/brinecove/surface_mapping.py',
                'platform/studio/atelier/__init__.py',
                'platform/studio/atelier/paths.py'),
               ('games/yorimichi/world/regions/brinecove/__init__.py',
                'games/yorimichi/world/regions/brinecove/falls.py',
                'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                'games/yorimichi/world/regions/brinecove/geom.py',
                'games/yorimichi/world/regions/brinecove/ground_sampling.py',
                'games/yorimichi/world/regions/brinecove/kit.py',
                'games/yorimichi/world/regions/brinecove/landmarks.py',
                'games/yorimichi/world/regions/brinecove/layout.py',
                'games/yorimichi/world/regions/brinecove/paths.py',
                'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                'games/yorimichi/world/regions/brinecove/procedural/hero_presence.py',
                'games/yorimichi/world/regions/brinecove/procedural/landmarks.py',
                'games/yorimichi/world/regions/brinecove/procedural/lighthouse.py',
                'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                'games/yorimichi/world/regions/brinecove/procedural/rock_cluster.py',
                'games/yorimichi/world/regions/brinecove/procedural/statue.py',
                'games/yorimichi/world/regions/brinecove/region.py',
                'games/yorimichi/world/regions/brinecove/rocks.py',
                'games/yorimichi/world/regions/brinecove/surface_mapping.py',
                'platform/studio/atelier/__init__.py',
                'platform/studio/atelier/paths.py')),
 'Market': ('market',
            ('games/yorimichi/assets/brinecove/export-parameters/Market.json',
             'games/yorimichi/world/regions/brinecove/__init__.py',
             'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
             'games/yorimichi/world/regions/brinecove/geom.py',
             'games/yorimichi/world/regions/brinecove/kit.py',
             'games/yorimichi/world/regions/brinecove/landmarks.py',
             'games/yorimichi/world/regions/brinecove/layout.py',
             'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
             'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
             'games/yorimichi/world/regions/brinecove/procedural/market.py',
             'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
             'games/yorimichi/world/regions/brinecove/region.py',
             'games/yorimichi/world/regions/brinecove/rocks.py',
             'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
            ('games/yorimichi/world/regions/brinecove/__init__.py',
             'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
             'games/yorimichi/world/regions/brinecove/geom.py',
             'games/yorimichi/world/regions/brinecove/kit.py',
             'games/yorimichi/world/regions/brinecove/landmarks.py',
             'games/yorimichi/world/regions/brinecove/layout.py',
             'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
             'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
             'games/yorimichi/world/regions/brinecove/procedural/market.py',
             'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
             'games/yorimichi/world/regions/brinecove/region.py',
             'games/yorimichi/world/regions/brinecove/rocks.py',
             'games/yorimichi/world/regions/brinecove/surface_mapping.py')),
 'Props': ('props',
           ('games/yorimichi/assets/brinecove/export-parameters/Props.json',
            'games/yorimichi/world/regions/brinecove/__init__.py',
            'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
            'games/yorimichi/world/regions/brinecove/geom.py',
            'games/yorimichi/world/regions/brinecove/kit.py',
            'games/yorimichi/world/regions/brinecove/landmarks.py',
            'games/yorimichi/world/regions/brinecove/layout.py',
            'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
            'games/yorimichi/world/regions/brinecove/procedural/props.py',
            'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
            'games/yorimichi/world/regions/brinecove/procedural/rowboat.py',
            'games/yorimichi/world/regions/brinecove/region.py',
            'games/yorimichi/world/regions/brinecove/rocks.py',
            'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
           ('games/yorimichi/world/regions/brinecove/__init__.py',
            'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
            'games/yorimichi/world/regions/brinecove/geom.py',
            'games/yorimichi/world/regions/brinecove/kit.py',
            'games/yorimichi/world/regions/brinecove/landmarks.py',
            'games/yorimichi/world/regions/brinecove/layout.py',
            'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
            'games/yorimichi/world/regions/brinecove/procedural/props.py',
            'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
            'games/yorimichi/world/regions/brinecove/procedural/rowboat.py',
            'games/yorimichi/world/regions/brinecove/region.py',
            'games/yorimichi/world/regions/brinecove/rocks.py',
            'games/yorimichi/world/regions/brinecove/surface_mapping.py')),
 'Rocks': ('terrain_dressing',
           ('games/yorimichi/assets/brinecove/export-parameters/Rocks.json',
            'games/yorimichi/world/regions/brinecove/__init__.py',
            'games/yorimichi/world/regions/brinecove/falls.py',
            'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
            'games/yorimichi/world/regions/brinecove/geom.py',
            'games/yorimichi/world/regions/brinecove/ground_sampling.py',
            'games/yorimichi/world/regions/brinecove/kit.py',
            'games/yorimichi/world/regions/brinecove/landmarks.py',
            'games/yorimichi/world/regions/brinecove/layout.py',
            'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
            'games/yorimichi/world/regions/brinecove/procedural/final_ground.py',
            'games/yorimichi/world/regions/brinecove/procedural/foam_ring.py',
            'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
            'games/yorimichi/world/regions/brinecove/procedural/rock_cluster.py',
            'games/yorimichi/world/regions/brinecove/procedural/shore_foam.py',
            'games/yorimichi/world/regions/brinecove/procedural/shoreline_foam.py',
            'games/yorimichi/world/regions/brinecove/procedural/terrain_dressing.py',
            'games/yorimichi/world/regions/brinecove/region.py',
            'games/yorimichi/world/regions/brinecove/rocks.py',
            'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
           ('games/yorimichi/world/regions/brinecove/__init__.py',
            'games/yorimichi/world/regions/brinecove/falls.py',
            'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
            'games/yorimichi/world/regions/brinecove/geom.py',
            'games/yorimichi/world/regions/brinecove/ground_sampling.py',
            'games/yorimichi/world/regions/brinecove/kit.py',
            'games/yorimichi/world/regions/brinecove/landmarks.py',
            'games/yorimichi/world/regions/brinecove/layout.py',
            'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
            'games/yorimichi/world/regions/brinecove/procedural/final_ground.py',
            'games/yorimichi/world/regions/brinecove/procedural/foam_ring.py',
            'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
            'games/yorimichi/world/regions/brinecove/procedural/rock_cluster.py',
            'games/yorimichi/world/regions/brinecove/procedural/shore_foam.py',
            'games/yorimichi/world/regions/brinecove/procedural/shoreline_foam.py',
            'games/yorimichi/world/regions/brinecove/procedural/terrain_dressing.py',
            'games/yorimichi/world/regions/brinecove/region.py',
            'games/yorimichi/world/regions/brinecove/rocks.py',
            'games/yorimichi/world/regions/brinecove/surface_mapping.py')),
 'Ships': ('ships',
           ('games/yorimichi/assets/brinecove/export-parameters/Ships.json',
            'games/yorimichi/assets/brinecove/models/galleon-figurehead.glb',
            'games/yorimichi/assets/brinecove/models/galleon-hull.glb',
            'games/yorimichi/assets/brinecove/models/galleon-hull.provenance.json',
            'games/yorimichi/assets/brinecove/models/pirate-queen-statue.glb',
            'games/yorimichi/assets/brinecove/models/ships-wheel.glb',
            'games/yorimichi/world/regions/brinecove/__init__.py',
            'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
            'games/yorimichi/world/regions/brinecove/geom.py',
            'games/yorimichi/world/regions/brinecove/kit.py',
            'games/yorimichi/world/regions/brinecove/layout.py',
            'games/yorimichi/world/regions/brinecove/paths.py',
            'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
            'games/yorimichi/world/regions/brinecove/procedural/hero_presence.py',
            'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
            'games/yorimichi/world/regions/brinecove/procedural/ship.py',
            'games/yorimichi/world/regions/brinecove/procedural/ships.py',
            'games/yorimichi/world/regions/brinecove/surface_mapping.py',
            'platform/studio/atelier/__init__.py',
            'platform/studio/atelier/paths.py'),
           ('games/yorimichi/world/regions/brinecove/__init__.py',
            'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
            'games/yorimichi/world/regions/brinecove/geom.py',
            'games/yorimichi/world/regions/brinecove/kit.py',
            'games/yorimichi/world/regions/brinecove/layout.py',
            'games/yorimichi/world/regions/brinecove/paths.py',
            'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
            'games/yorimichi/world/regions/brinecove/procedural/hero_presence.py',
            'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
            'games/yorimichi/world/regions/brinecove/procedural/ship.py',
            'games/yorimichi/world/regions/brinecove/procedural/ships.py',
            'games/yorimichi/world/regions/brinecove/surface_mapping.py',
            'platform/studio/atelier/__init__.py',
            'platform/studio/atelier/paths.py')),
 'TownLower': ('lower_town',
               ('games/yorimichi/assets/brinecove/export-parameters/TownLower.json',
                'games/yorimichi/world/regions/brinecove/__init__.py',
                'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                'games/yorimichi/world/regions/brinecove/geom.py',
                'games/yorimichi/world/regions/brinecove/kit.py',
                'games/yorimichi/world/regions/brinecove/landmarks.py',
                'games/yorimichi/world/regions/brinecove/layout.py',
                'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                'games/yorimichi/world/regions/brinecove/procedural/covered.py',
                'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
                'games/yorimichi/world/regions/brinecove/procedural/lower_town.py',
                'games/yorimichi/world/regions/brinecove/procedural/pave_band.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_material.py',
                'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                'games/yorimichi/world/regions/brinecove/procedural/split_lot.py',
                'games/yorimichi/world/regions/brinecove/region.py',
                'games/yorimichi/world/regions/brinecove/rocks.py',
                'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
               ('games/yorimichi/world/regions/brinecove/__init__.py',
                'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                'games/yorimichi/world/regions/brinecove/geom.py',
                'games/yorimichi/world/regions/brinecove/kit.py',
                'games/yorimichi/world/regions/brinecove/landmarks.py',
                'games/yorimichi/world/regions/brinecove/layout.py',
                'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                'games/yorimichi/world/regions/brinecove/procedural/covered.py',
                'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
                'games/yorimichi/world/regions/brinecove/procedural/lower_town.py',
                'games/yorimichi/world/regions/brinecove/procedural/pave_band.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_material.py',
                'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                'games/yorimichi/world/regions/brinecove/procedural/split_lot.py',
                'games/yorimichi/world/regions/brinecove/region.py',
                'games/yorimichi/world/regions/brinecove/rocks.py',
                'games/yorimichi/world/regions/brinecove/surface_mapping.py')),
 'TownUpper': ('upper_town',
               ('games/yorimichi/assets/brinecove/export-parameters/TownUpper.json',
                'games/yorimichi/world/regions/brinecove/__init__.py',
                'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                'games/yorimichi/world/regions/brinecove/geom.py',
                'games/yorimichi/world/regions/brinecove/kit.py',
                'games/yorimichi/world/regions/brinecove/landmarks.py',
                'games/yorimichi/world/regions/brinecove/layout.py',
                'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                'games/yorimichi/world/regions/brinecove/procedural/covered.py',
                'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
                'games/yorimichi/world/regions/brinecove/procedural/lower_street_slabs.py',
                'games/yorimichi/world/regions/brinecove/procedural/pave_band.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_material.py',
                'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                'games/yorimichi/world/regions/brinecove/procedural/split_lot.py',
                'games/yorimichi/world/regions/brinecove/procedural/stair_apron.py',
                'games/yorimichi/world/regions/brinecove/procedural/terrace_stair.py',
                'games/yorimichi/world/regions/brinecove/procedural/terrace_stair_plan.py',
                'games/yorimichi/world/regions/brinecove/procedural/upper_town.py',
                'games/yorimichi/world/regions/brinecove/region.py',
                'games/yorimichi/world/regions/brinecove/rocks.py',
                'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
               ('games/yorimichi/world/regions/brinecove/__init__.py',
                'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                'games/yorimichi/world/regions/brinecove/geom.py',
                'games/yorimichi/world/regions/brinecove/kit.py',
                'games/yorimichi/world/regions/brinecove/landmarks.py',
                'games/yorimichi/world/regions/brinecove/layout.py',
                'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                'games/yorimichi/world/regions/brinecove/procedural/covered.py',
                'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py',
                'games/yorimichi/world/regions/brinecove/procedural/lower_street_slabs.py',
                'games/yorimichi/world/regions/brinecove/procedural/pave_band.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py',
                'games/yorimichi/world/regions/brinecove/procedural/paving_material.py',
                'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                'games/yorimichi/world/regions/brinecove/procedural/split_lot.py',
                'games/yorimichi/world/regions/brinecove/procedural/stair_apron.py',
                'games/yorimichi/world/regions/brinecove/procedural/terrace_stair.py',
                'games/yorimichi/world/regions/brinecove/procedural/terrace_stair_plan.py',
                'games/yorimichi/world/regions/brinecove/procedural/upper_town.py',
                'games/yorimichi/world/regions/brinecove/region.py',
                'games/yorimichi/world/regions/brinecove/rocks.py',
                'games/yorimichi/world/regions/brinecove/surface_mapping.py')),
 'Understory': ('vegetation',
                ('games/yorimichi/assets/brinecove/export-parameters/Understory.json',
                 'games/yorimichi/world/regions/brinecove/__init__.py',
                 'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                 'games/yorimichi/world/regions/brinecove/geom.py',
                 'games/yorimichi/world/regions/brinecove/kit.py',
                 'games/yorimichi/world/regions/brinecove/layout.py',
                 'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                 'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                 'games/yorimichi/world/regions/brinecove/procedural/vegetation.py',
                 'games/yorimichi/world/regions/brinecove/surface_mapping.py'),
                ('games/yorimichi/world/regions/brinecove/__init__.py',
                 'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
                 'games/yorimichi/world/regions/brinecove/geom.py',
                 'games/yorimichi/world/regions/brinecove/kit.py',
                 'games/yorimichi/world/regions/brinecove/layout.py',
                 'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
                 'games/yorimichi/world/regions/brinecove/procedural/random_state.py',
                 'games/yorimichi/world/regions/brinecove/procedural/vegetation.py',
                 'games/yorimichi/world/regions/brinecove/surface_mapping.py'))}

CODE_DIGESTS = {'games/yorimichi/brinecove_atomic_build.py': '793a575d1282ce165e0d6bad516bf0d86f37d0d42a7d03302e785842a93cfd94',
 'games/yorimichi/region_exports.py': '3b30f0b35a559adacd08df7149c268213c5b481d7e284fbcf478db002e6ee3ed',
 'games/yorimichi/world/mesh_pieces.py': '78293e306a8a1c7d1ff4efde45dd16e22ed371d2a4ec80ef826a1abcf946c608',
 'games/yorimichi/world/random_stream.py': 'c8416c00a0e4efe014de70817ec3ba0dcd9e0d406746ab7f4da120c0b650fd3d',
 'games/yorimichi/world/region_mesh_parts.py': 'd93f2c4deb9c2c08bd730b7a4f1476b0ccf7a3dc7de2f604363c2ce8d4cc4725',
 'games/yorimichi/world/region_mesh_set.py': '667a3df446981acd5f97056d4cda4e503e4cd29370decb44ce9ad2d5156a042b',
 'games/yorimichi/world/region_plan_files.py': '7451f36a391a5bd6a4c7e12a489b3ec8da64df3a14843257b7626e3958b736c6',
 'games/yorimichi/world/region_query.py': 'fa96910b6715daa5ed9cde939b9a8ed7b9677ea869983c385849e2785e3dce15',
 'games/yorimichi/world/regions/brinecove/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
 'games/yorimichi/world/regions/brinecove/falls.py': 'd1af6c2bc498ef75ffeb23195aee452ede826a0768e635f10d2a35cef9daeffb',
 'games/yorimichi/world/regions/brinecove/foliage_atlas.py': '3de6eff0d43ffe0e6fb667c6087118887b8f1f470084b71884a81dd8708be878',
 'games/yorimichi/world/regions/brinecove/geom.py': '7bf56676bb3008f23eae82f3f7283807ecb861bb03e1f6f1a845bc4395a58bd3',
 'games/yorimichi/world/regions/brinecove/geometry_finish.py': '1e2a7f63ee7fb77c521c424d5b3e85f3fac9fbc31e27a81e91f5b0c0b0d8f87f',
 'games/yorimichi/world/regions/brinecove/ground_sampling.py': '1c037da5fa0622dc89e4b0e2366b0c397166940ed444f8bf39442f70871cc463',
 'games/yorimichi/world/regions/brinecove/kit.py': 'eca78952598f4cabfba7cfcb7f8d6e78bf0c579642f44a7120dc0562232c62fd',
 'games/yorimichi/world/regions/brinecove/landmarks.py': 'b2906fb60ac9ffcdd1071c2bf16e702fe8ae49b9c0de65645734c4210d1e69c4',
 'games/yorimichi/world/regions/brinecove/layout.py': '13dbad8c737a43479179271f727701400abd6a2c9e35dea8f51e3299f4158462',
 'games/yorimichi/world/regions/brinecove/logical_catalogue.py': '25d0cc3cdf6c8b3dcecdbe22e029eaae6c0dd3fc086f8dce3a5fc4411bd4853b',
 'games/yorimichi/world/regions/brinecove/paths.py': 'aa56e80a16a93d8cf8de1b71ec51176c710a90969955938827984b6b3b2d0dec',
 'games/yorimichi/world/regions/brinecove/piece_inputs.py': '38bc8b2aad9e256bcbfd522495a6ea3105fbb4bb619ac6a974c43763ba90bfdd',
 'games/yorimichi/world/regions/brinecove/plan_component.py': 'f45edc27e3f10fdc324b767d8fb289b5a52533846e05f22beda650803bf98ae4',
 'games/yorimichi/world/regions/brinecove/procedural/__init__.py': '0c21b3cbe718673b99b12dd6d1752e0a8a46441ca3e107bc7892eb5518b265a2',
 'games/yorimichi/world/regions/brinecove/procedural/covered.py': '2b4efb8553f8ec2ebbd27495eadabb5edf37f427738cfc73ecbc718e6d780619',
 'games/yorimichi/world/regions/brinecove/procedural/final_ground.py': '6b06574209590ff7bb573000ad5ed116209023d2f971955ad354d5d608068da6',
 'games/yorimichi/world/regions/brinecove/procedural/foam_ring.py': 'ef05b0c837abf63b41fc75d953c4676116756f17bced7e23c366e39b72a9f08f',
 'games/yorimichi/world/regions/brinecove/procedural/geometry_policy.py': '84df115a74450d0b382055e02c0f12886386cc0fb174fe772cc39314e45f1452',
 'games/yorimichi/world/regions/brinecove/procedural/harbor.py': '5f8ca10fff9c33a1005daa70e7b8224999e89607ac1eb392eaac7587a00f507c',
 'games/yorimichi/world/regions/brinecove/procedural/hero_presence.py': '70b97c3ec384325a6b8ccb31954119cf844c49de0e8b76fd8e400efa6c113669',
 'games/yorimichi/world/regions/brinecove/procedural/landmarks.py': '7b3eb7edf4db4f9580762807348b0ed89b3d3f7b65dc4ac574c9e6d2abac653e',
 'games/yorimichi/world/regions/brinecove/procedural/lighthouse.py': '5ee614d323ceff93e5f4e16ca58123fec2e1925fdc9efbc44b127a539c080a8c',
 'games/yorimichi/world/regions/brinecove/procedural/lower_street_slabs.py': '1485a142c2147972d54dcc3c7feab2a120adfe29cdba51b10574714144bd03fe',
 'games/yorimichi/world/regions/brinecove/procedural/lower_town.py': '88beb1ddf77c96f38dbdc2abe12ab44b8958b8153c6b4de3e12a2f460eab3cfb',
 'games/yorimichi/world/regions/brinecove/procedural/market.py': 'a91dbbc160ec7bfa2cf8f13a24c7dfef3772188db20d70e1c1fbd0205669712d',
 'games/yorimichi/world/regions/brinecove/procedural/pave_band.py': '2d66483d7236e5a1afd45d61c149dd6d0e505a73ed458576a529818b3f7b7794',
 'games/yorimichi/world/regions/brinecove/procedural/paving.py': '022c732bcd4f159d951865c9f75d9d23d3fbc46a3ce9fe3839172c1ffb097c04',
 'games/yorimichi/world/regions/brinecove/procedural/paving_grid.py': '4621c0137d86706d253db54c830184a553a8d253c8683e3e657b67820d4a1cf2',
 'games/yorimichi/world/regions/brinecove/procedural/paving_material.py': '7477991b74337da1de364bcae1517ba5012e848a50fa2cb59167bf27a808e72d',
 'games/yorimichi/world/regions/brinecove/procedural/props.py': 'd3677a0a381bcb8761296b6d74a0fecb526c05dd5858b57253a6c4267c4a70fc',
 'games/yorimichi/world/regions/brinecove/procedural/random_state.py': '8871613b7413b2be0cb65f3150b49df11d35d7941e5b808b7b2019fa14db5096',
 'games/yorimichi/world/regions/brinecove/procedural/rock_cluster.py': 'cdf128b00fd7da6c730abd88bbf4fd58e0ac48e29ec7da08f88e36d4638a6e5c',
 'games/yorimichi/world/regions/brinecove/procedural/rowboat.py': '399040984a53f1e4f00229869503badda1981c3ecdd171f59487813864b7b81b',
 'games/yorimichi/world/regions/brinecove/procedural/ship.py': 'df2893bb031c42c0e8f197f4f85424c45cd82fe865d4c0d883f1a1c978ae3fc6',
 'games/yorimichi/world/regions/brinecove/procedural/ships.py': 'ab301366128b7bd7f8fb3c3fc529368facc6e550847961d72c1eee06cce02695',
 'games/yorimichi/world/regions/brinecove/procedural/shore_foam.py': '5dca97f28850c5ecde124b74b47c483dc947ea126ae6f684cb977c54009c22bc',
 'games/yorimichi/world/regions/brinecove/procedural/shoreline_foam.py': 'da9f067850747552340d5148b0b69c5af935955337a5d1ac70af43267a583eec',
 'games/yorimichi/world/regions/brinecove/procedural/split_lot.py': '5621632f810ebe360ebc4329ddf26cb38d8a37cf3254636955be440e4f8a271b',
 'games/yorimichi/world/regions/brinecove/procedural/stair_apron.py': '9d72667810682e3af7b1fe820f7c5a24400ea2909fbed12f972683ee8151a9d7',
 'games/yorimichi/world/regions/brinecove/procedural/statue.py': 'd6902c492a8b98ede01d0dd2483ea7a0749aa13140e1bfe415bc3cfccd02428f',
 'games/yorimichi/world/regions/brinecove/procedural/terrace_stair.py': '9ccc0ece4ce96b9b6ac5d278f09b394775f93d69e478fcf7d0f89b0c9c3d33c7',
 'games/yorimichi/world/regions/brinecove/procedural/terrace_stair_plan.py': 'c0b9263e087a2ff163c7c668e2a1c5ff2d00ff216cd7dc28908e8ce62ddd2471',
 'games/yorimichi/world/regions/brinecove/procedural/terrain_dressing.py': 'c78ec039174c1cc1d6752ad2845d8289b5b948d320173946a01f20a7b67514ce',
 'games/yorimichi/world/regions/brinecove/procedural/upper_town.py': '27c1606d59a73ccb411c5729e80a61d5263d60e28fa83caae84fb6f4507e1ef2',
 'games/yorimichi/world/regions/brinecove/procedural/vegetation.py': '3e1ef24861285ac4bb7cdc72866b44f17c53f868cf8144db18396e30f036ee80',
 'games/yorimichi/world/regions/brinecove/region.py': 'd30f19ee9aa548093535146367893cf12b7d33d1c158527812b8e1796f56146d',
 'games/yorimichi/world/regions/brinecove/rim_schema.py': '51a03751482c5bceaab1532fd6825f3697c091737d015d5123a2f975e5903f87',
 'games/yorimichi/world/regions/brinecove/rocks.py': '4d58b64dac8ea3e37abcedb10984947d94bf16d8e3b680d6dbc1055cb82db7ef',
 'games/yorimichi/world/regions/brinecove/surface_mapping.py': 'cc8e24bcb2454180ac4035394806acbe49b0cee7761abc3b1e5bea3101ede37f',
 'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc',
 'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15',
 'platform/studio/atelier/atomic_files.py': '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78',
 'platform/studio/atelier/build_batch_source.py': '2a61a96a1929832346327d0465a4c18e419c2e4e686d4a8cc7e06c436608195c',
 'platform/studio/atelier/build_batch_worker.py': 'b8812145d851943019b0415a330b27a6996b8921ecd4a9a146dbe5c8d937d22d',
 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6',
 'platform/studio/atelier/gltf.py': 'f5d5bb2bcd2e4fd22c534c49231080057ca81c9fa2fd4855d6978bd0d8d0358d',
 'platform/studio/atelier/mesh_cells.py': 'db88ba7bf0803fcae6abccbbc20fbc6c4e10965d3d721e770317640298ea887f',
 'platform/studio/atelier/mesh_collision.py': 'c2d7813ef2194ce82d9d2f908bb0b1c9919462c1c046db527167d18838c82183',
 'platform/studio/atelier/mesh_ir.py': '1522b888aefd3b7b0a3e63135972a45e5d9b11c2b1cdf4489b7ffa073a2d1cad',
 'platform/studio/atelier/mesh_materials.py': 'f0c4f63670c7d51d0769eef9128e587fdb65ee7cf1aab7f6fbbdb3f0479623e9',
 'platform/studio/atelier/mesh_partition.py': 'd6ab94f80cf8f3f220d422a194e8bd4e7a171c31ad9da56de9ecb1853a8b9ea3',
 'platform/studio/atelier/model_export.py': '0ba9b3d7a54d8653b4c2674cded755487951fe4d213098a046977983cf4768c2',
 'platform/studio/atelier/model_files.py': '349c53215e39d939950b972e4353747d4dff560eaf7dda49325774398561ccbb',
 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}

def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) in (tuple, list):
        return len(actual) == len(expected) and all((_exact(a, b) for a, b in zip(actual, expected)))
    return actual == expected

def _read(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, path.relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedBrinecoveComponent(f'linked, missing or invalid source/data file: {path}') from error

def _role(checkout, path, *, directory=False):
    """Inspect only the role and nofollow ancestors; large data contents stay unopened."""
    from atelier.build_v2.controller_client import _open_root
    try:
        path.relative_to(checkout)
        descriptor = _open_root(path if directory else path.parent)
        try:
            if not directory and (not stat.S_ISREG(os.stat(path.name, dir_fd=descriptor, follow_symlinks=False).st_mode)):
                raise ValueError('not a regular file')
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as error:
        raise UnsupportedBrinecoveComponent(f'linked, missing or invalid input role: {path}') from error

def _output(path, *, directory):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            current = current.parent
            continue
        except OSError as error:
            raise UnsupportedBrinecoveComponent('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedBrinecoveComponent('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedBrinecoveComponent('linked output ancestry') from error
            return
        current = current.parent

def _json(checkout, path):

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(_read(checkout, path), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as error:
        raise UnsupportedBrinecoveComponent('invalid raw JSON declaration') from error

def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedBrinecoveComponent('invalid captured source structure') from error

def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

def _closure(checkout, world, studio, script, builder, expected, constructor_roles):
    from atelier import build, paths
    allowed = set(expected)
    def read(path):
        if path not in allowed:
            raise UnsupportedBrinecoveComponent('unknown source import candidate')
        _read(checkout, path)
    def anchor(path):
        if path == paths.STUDIO:
            return studio
        if path == paths.STUDIO / 'atelier':
            return studio / 'atelier'
        return path
    class Checked(build._FastImportScanner.__bases__[0]):
        def resolve(self, root, parts):
            found = super().resolve(anchor(root), parts)
            for path in found:
                read(path)
            return found
    scanner = Checked()
    observed = set()
    for source, roles in ((script, SCRIPT_ROLES), (builder, constructor_roles)):
        actual = tuple(scanner.local_imports(source, (world, world / 'regions', studio)))
        if actual != tuple(checkout / role for role in roles):
            raise UnsupportedBrinecoveComponent('original source closure differs')
        for path in actual:
            read(path)
        observed.update(actual)
    return observed


def qualify_brinecove_component(step, *, checkout: Path, output_root: Path) -> BrinecoveComponent:
    """@cc [owner:fontanierh,label:correctness;safety] closed-coastal-component-observation
    Bind only the nine original component declarations, ordered raw/code roles, exact
    Batch and three owned products, and original verifier code/defaults/globals. Fixed
    dynamic builders MUST match the literal catalogue and independently checked source
    closures. Generated rim/query/plan data MUST NOT be opened. Cold missing output
    tails are permitted without writes. Refuse aliases, unknown controls and source
    changes; never execute constructors/verifiers or grant future tasks, repair or Finish.
    """
    from atelier import build, build_products
    from atelier.build_v2.legacy_qualification import CapturedCode, IdentityBinding, UnsupportedOrigin, verify_callable
    checkout, output_root = Path(checkout), Path(output_root)
    prefix = 'world.brinecove.geometry.SM_BC_'
    if (type(step) is not build.Step or type(getattr(step, 'name', None)) is not str
            or not step.name.startswith(prefix) or step.name[len(prefix):] not in COMPONENTS
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedBrinecoveComponent('not an original component Step and absolute anchors')
    if any(os.environ.get(name, '').strip() for name in (
            'ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedBrinecoveComponent('not the default shipped context')
    key = step.name[len(prefix):]
    builder, tail_roles, constructor_roles = COMPONENTS[key]
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    studio = checkout / 'platform/studio'
    region = world / 'regions/brinecove'
    script = region / 'plan_component.py'
    parameter = game / 'assets/brinecove/export-parameters' / (key + '.json')
    primary = output_root / 'planned_exports/brinecove' / ('SM_BC_' + key)
    query = output_root / 'brinecove/query-data' / ('SM_BC_' + key + '.npz')
    paving = output_root / 'brinecove-data/paving' / (key + '.json')
    rim = output_root / 'brinecove-data/final-rim.json'
    arguments = ('--asset', key, '--builder', builder, '--context', str(parameter), '--rim', str(rim),
                 '--paving-output', str(paving), '--query-output', str(query), '--output', str(primary))
    products = ((f'brinecove.geometry.SM_BC_{key}', (primary,)),
                (f'brinecove.query.SM_BC_{key}', (query,)), (f'brinecove.paving.{key}', (paving,)))
    defaults = dict(deferred_inputs=[], needs=[], after=[], heavy=True, pool_roots=[], explicit=False,
        cutoff=False, references=[], cache=True, audit=False, optional_inputs=[], queries=[], toolchain=True,
        cook_recovery=None, checkpoint_previous_needs=None, checkpoint_restore=None, checkpoint_outputs=(),
        candidate_scope=None, replan=False, controller=None, outputs=[], reads=['brinecove.rim_data'],
        about='construct only logical mesh SM_BC_' + key)
    if (set(vars(step)) != set(defaults) | {'name', 'commands', 'inputs', 'products', 'batch', 'verify'}
            or any(not _exact(vars(step)[name], value) for name, value in defaults.items())):
        raise UnsupportedBrinecoveComponent('original Step controls differ')
    batch = step.batch
    if (type(batch) is not build.Batch or set(vars(batch)) != {'group', 'runtime_env', 'max_seconds'}
            or not _exact(batch.group, 'brinecove logical geometry') or not _exact(batch.runtime_env, ())
            or type(batch.max_seconds) is not float or batch.max_seconds != 240.):
        raise UnsupportedBrinecoveComponent('original Batch differs')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedBrinecoveComponent('expected one original Blender command')
    command = step.commands[0]
    if (type(command) is not build.Blender or set(vars(command)) != {'script', 'args', 'threads', 'factory_startup', 'env'}
            or not _exact(command.script, script) or not _exact(command.args, arguments)
            or type(command.threads) is not int or command.threads != 3 or command.factory_startup is not True
            or not _exact(command.env, (('PYTHONHASHSEED', '0'),))):
        raise UnsupportedBrinecoveComponent('original Blender command differs')
    if type(step.products) is not list or len(step.products) != 3:
        raise UnsupportedBrinecoveComponent('original products differ')
    for product, (name, owned) in zip(step.products, products):
        if (type(product) is not build_products.Product
                or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
                or not _exact(product.name, name) or not _exact(product.paths, owned)
                or product.collection is not None or product.bounds is not None or not _exact(product.optional_paths, ())):
            raise UnsupportedBrinecoveComponent('original products differ')
    inputs = [*(checkout / role for role in SCRIPT_ROLES), studio / 'atelier/build_batch_source.py',
              studio / 'atelier/build_batch_worker.py', *sorted(checkout / role for role in tail_roles)]
    if not _exact(step.inputs, inputs):
        raise UnsupportedBrinecoveComponent('original ordered inputs differ')
    code_roles = tuple(sorted({*SCRIPT_ROLES, 'platform/studio/atelier/build_batch_source.py',
                              'platform/studio/atelier/build_batch_worker.py',
                              *(role for role in tail_roles if role.endswith('.py'))}))
    code = tuple(checkout / role for role in code_roles)
    control_roles = ('games/yorimichi/brinecove_atomic_build.py', 'games/yorimichi/region_exports.py',
                     'games/yorimichi/world/regions/brinecove/logical_catalogue.py')
    for path in (checkout, checkout / 'games', game, world, world / 'regions', region,
                 checkout / 'platform', studio):
        _role(checkout, path, directory=True)
    for path in inputs:
        _role(checkout, path)
    for path, directory in ((output_root, True), (primary, True), (query, False), (paving, False), (rim, False)):
        _output(path, directory=directory)
    for role in (*code_roles, *control_roles):
        path = checkout / role
        _role(checkout, path)
        if _digest(_ast(checkout, path)) != CODE_DIGESTS[role]:
            raise UnsupportedBrinecoveComponent('original source structure differs: ' + role)
    doc = _json(checkout, parameter)
    if (type(doc) is not dict or set(doc) != {'schema', 'asset', 'seed', 'prefix_words'}
            or type(doc['schema']) is not int or doc['schema'] != 1 or doc['asset'] != key
            or type(doc['seed']) is not int or type(doc['prefix_words']) is not int
            or not 0 <= doc['prefix_words'] <= 1_000_000):
        raise UnsupportedBrinecoveComponent('invalid selected constructor parameters')
    observed = _closure(checkout, world, studio, script, region / 'procedural' / (builder + '.py'),
                        code, constructor_roles)
    observed.update(path for path in inputs if path.suffix == '.py')
    if tuple(sorted(observed)) != code:
        raise UnsupportedBrinecoveComponent('selected union source closure differs')
    if type(step.verify) is not types.FunctionType or vars(step.verify):
        raise UnsupportedBrinecoveComponent('not the original verifier')
    captured = CapturedCode(str(game / 'region_exports.py'), _read(checkout, game / 'region_exports.py'))
    try:
        verifier = verify_callable(step.verify, captured, qualname='steps.<locals>.complete',
            namespace=step.verify.__globals__, defaults=(primary, False), keyword_defaults=None, closures={},
            globals_={'WORLD': world}, builtins_={'str': IdentityBinding(str)})
    except UnsupportedOrigin as error:
        raise UnsupportedBrinecoveComponent('original verifier bindings differ') from error
    # region_exports.py is explicitly verifier-owned source, independently captured
    # through CallableObservation; it is not silently added to producer code roles.
    return BrinecoveComponent(step.name, script, arguments, tuple(inputs), (rim,), code, products, verifier)
