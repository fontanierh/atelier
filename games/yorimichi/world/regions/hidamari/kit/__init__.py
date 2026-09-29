"""Reference-led building kit for Hidamari's ordinary blocks.

Each module in this package designs one building type. It exports
    ASSETS = {'HD_Shop_03': 0, 'HD_Shop_11': 1}          # mesh name -> variant key
    def build(name, variant, lettering) -> village.build.Mesh named `name`
The Blender builder (hidamari/build.py) lets these override the legacy shop(i) boxes, so the
existing city layout keeps its placements: yaw 0 fronts face -Y (the street), footprint
about 20-23 m wide x 15-16 m deep, front wall near y=-d/2, colliders required for anything
the player can walk into. Briefs live in briefs.json; renders/refs in docs/hidamari/kit/<slug>/.
"""
import importlib,pkgutil

def builders(lettering):
    out={}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith('_'):continue
        mod=importlib.import_module(f'hidamari.kit.{info.name}')
        for name,variant in getattr(mod,'ASSETS',{}).items():
            out[name]=(lambda mod=mod,name=name,variant=variant:mod.build(name,variant,lettering))
    return out
