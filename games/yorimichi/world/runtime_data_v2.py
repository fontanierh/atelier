"""Remaining runtime staging through a zero-argument, path-bound recipe callback."""
import importlib.util
from pathlib import Path
import shutil


def stage(files=(), courses=None, scene=None, validator=None):
    """@cc [owner:fontanierh,label:correctness] bound-runtime-data-stage
    The original keyed course validator MUST run before any runtime staging write.
    Every required frozen source MUST copy2 to its exact declared Content/Data path;
    no file MAY be skipped, substituted, discovered from generated state or staged
    through an ambient game Context/content locator. Frozen path defaults MUST bind
    wholly inside the recipe-owned view. Existing unrelated runtime files MUST stay.
    """
    view=Path(__file__).resolve().parents[3]
    def path(value):
        if not isinstance(value,Path) or not value.is_absolute() or not value.is_relative_to(view) or value.resolve()!=value:
            raise ValueError('Runtime staging requires exact bound paths inside the owned view')
        return value
    courses,scene,validator=map(path,(courses,scene,validator))
    if not validator.is_file():raise ValueError('Missing keyed original course validator')
    spec=importlib.util.spec_from_file_location('runtime_stage_original_courses',validator)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    original.load(courses,scene)
    destination_root=view/'games/yorimichi/unreal/Content/Data'
    selected=[];seen=set()
    for source,destination in files:
        source,destination=path(source),path(destination)
        if (not source.is_file() or not destination.is_relative_to(destination_root) or destination==destination_root
                or destination in seen or (destination.exists() and not destination.is_file())):
            raise ValueError('Missing source or conflicting declared runtime destination')
        seen.add(destination);selected.append((source,destination))
    if not selected:raise ValueError('Runtime staging requires its complete nonempty file table')
    for source,destination in selected:
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
