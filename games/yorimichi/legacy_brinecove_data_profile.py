"""Finite source observations for the original coastal rim and placement JSON tasks."""
from dataclasses import dataclass
import ast
import hashlib
import os
from pathlib import Path
import stat

ROLES = {'world.brinecove.rim_data': {'script': 'games/yorimichi/world/regions/brinecove/rim_data.py', 'product': 'brinecove.rim_data', 'code': {'games/yorimichi/world/regions/brinecove/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6', 'games/yorimichi/world/regions/brinecove/boundary.py': '899069fce56e5bf9909856482c1e3b163498dd430d876c8db1476db866827d20', 'games/yorimichi/world/regions/brinecove/region.py': 'd30f19ee9aa548093535146367893cf12b7d33d1c158527812b8e1796f56146d', 'games/yorimichi/world/regions/brinecove/rim_data.py': '1f09a0ad040a11bfad63815756839fc4aa9e5cc78b64c05e64417207ff55c623', 'games/yorimichi/world/regions/brinecove/rim_schema.py': '51a03751482c5bceaab1532fd6825f3697c091737d015d5123a2f975e5903f87', 'games/yorimichi/world/terrain_product.py': '9bf1a8e738ab7a2a1da44d3d6bee65f348ad2369c48590adf7ad0dcfc3544bd1', 'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc', 'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15', 'platform/studio/atelier/atomic_files.py': '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78', 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6', 'platform/studio/atelier/model_files.py': '349c53215e39d939950b972e4353747d4dff560eaf7dda49325774398561ccbb', 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}}, 'world.brinecove.placements': {'script': 'games/yorimichi/world/regions/brinecove/placement_data.py', 'product': 'brinecove.placements', 'code': {'games/yorimichi/world/regions/brinecove/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6', 'games/yorimichi/world/regions/brinecove/foliage_atlas.py': '3de6eff0d43ffe0e6fb667c6087118887b8f1f470084b71884a81dd8708be878', 'games/yorimichi/world/regions/brinecove/foliage_placements.py': '3be958744285903626a13a411c3a1bcacf3d3c1dba8c9064a12993b71f0c2e27', 'games/yorimichi/world/regions/brinecove/geom.py': '7bf56676bb3008f23eae82f3f7283807ecb861bb03e1f6f1a845bc4395a58bd3', 'games/yorimichi/world/regions/brinecove/geometry_finish.py': '1e2a7f63ee7fb77c521c424d5b3e85f3fac9fbc31e27a81e91f5b0c0b0d8f87f', 'games/yorimichi/world/regions/brinecove/hero_math.py': 'fa2b16d741461ae297bc849ec5b07404b2f6a83fb17c52a175d3f76ec9c92118', 'games/yorimichi/world/regions/brinecove/hero_placements.py': '46a4ea317f6b40e441f2a4a80428e2e25785f7f0c98bbec75b9ea6df47b65b49', 'games/yorimichi/world/regions/brinecove/hero_sources.py': '2471e544497226f149247f481acec5babdc0b39530821e6f63083465eced0988', 'games/yorimichi/world/regions/brinecove/kit.py': 'eca78952598f4cabfba7cfcb7f8d6e78bf0c579642f44a7120dc0562232c62fd', 'games/yorimichi/world/regions/brinecove/landmarks.py': 'b2906fb60ac9ffcdd1071c2bf16e702fe8ae49b9c0de65645734c4210d1e69c4', 'games/yorimichi/world/regions/brinecove/layout.py': '13dbad8c737a43479179271f727701400abd6a2c9e35dea8f51e3299f4158462', 'games/yorimichi/world/regions/brinecove/paths.py': 'aa56e80a16a93d8cf8de1b71ec51176c710a90969955938827984b6b3b2d0dec', 'games/yorimichi/world/regions/brinecove/placement_data.py': '6c394333b0265535b66849f8442d6406fb3fef15425eb01c2c426808be314b3f', 'games/yorimichi/world/regions/brinecove/region.py': 'd30f19ee9aa548093535146367893cf12b7d33d1c158527812b8e1796f56146d', 'games/yorimichi/world/regions/brinecove/rim_schema.py': '51a03751482c5bceaab1532fd6825f3697c091737d015d5123a2f975e5903f87', 'games/yorimichi/world/regions/brinecove/rocks.py': '4d58b64dac8ea3e37abcedb10984947d94bf16d8e3b680d6dbc1055cb82db7ef', 'games/yorimichi/world/regions/brinecove/runtime_data.py': '5dffaa404ee7ae006d1687a1b6155cd3076c463682e683473d958968bf7832b8', 'games/yorimichi/world/regions/brinecove/surface_mapping.py': 'cc8e24bcb2454180ac4035394806acbe49b0cee7761abc3b1e5bea3101ede37f', 'games/yorimichi/world/source_registry.py': '8e0a464b917fc48cf12b1093a0e63913f1f2522328caa39c59c2c5a3df36c0df', 'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc', 'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15', 'platform/studio/atelier/atomic_files.py': '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78', 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6', 'platform/studio/atelier/mesh_partition.py': 'd6ab94f80cf8f3f220d422a194e8bd4e7a171c31ad9da56de9ecb1853a8b9ea3', 'platform/studio/atelier/model_files.py': '349c53215e39d939950b972e4353747d4dff560eaf7dda49325774398561ccbb', 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}}}
CONSTRUCTOR_AST = '9a16d450455f9517065e864f935d6d00ffffa339b0bfef1899106a129ae7d793'


class UnsupportedBrinecoveData(ValueError):
    """The original source/data/output projection cannot be established."""


@dataclass(frozen=True)
class BrinecoveData:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]


def _source(checkout,path):
    from atelier.build_v2.controller_client import _read_at, MAX_SOURCE_FILE_BYTES
    try:return _read_at(checkout,path.relative_to(checkout).as_posix(),MAX_SOURCE_FILE_BYTES)
    except (OSError,ValueError) as error:raise UnsupportedBrinecoveData('source is linked, missing or outside checkout') from error


def _output(path):
    from atelier.build_v2.controller_client import _open_root
    current=path
    while True:
        try:info=current.lstat()
        except FileNotFoundError:current=current.parent;continue
        except OSError as error:raise UnsupportedBrinecoveData('output ancestry cannot be inspected') from error
        if not (stat.S_ISREG(info.st_mode) if current==path else stat.S_ISDIR(info.st_mode)):
            raise UnsupportedBrinecoveData('output ancestry is linked or foreign')
        try:fd=_open_root(current if stat.S_ISDIR(info.st_mode) else current.parent);os.close(fd)
        except OSError as error:raise UnsupportedBrinecoveData('output ancestry is not anchored') from error
        return


def _digest(raw):
    try:tree=ast.parse(raw)
    except (SyntaxError,ValueError) as error:raise UnsupportedBrinecoveData('invalid source syntax') from error
    return hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()


def _model_inputs(directory):
    from atelier.build_v2.controller_client import _open_root
    try:
        fd=_open_root(directory)
        try:
            before=os.fstat(fd);result=[]
            with os.scandir(fd) as entries:
                for entry in entries:
                    if Path(entry.name).suffix=='.glb' or entry.name.endswith('.provenance.json'):
                        if not stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                            raise UnsupportedBrinecoveData('model role is linked or special')
                        result.append(directory/entry.name)
            after=os.fstat(fd)
            if (before.st_dev,before.st_ino,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_mtime_ns):
                raise UnsupportedBrinecoveData('model membership changed during observation')
            return tuple(result)
        finally:os.close(fd)
    except OSError as error:raise UnsupportedBrinecoveData('model directory is not anchored') from error


def qualify_brinecove_data(step,*,checkout:Path,output_root:Path)->BrinecoveData:
    """@cc [owner:fontanierh,label:correctness;safety] coastal-json-data-observation
    Only the two original rim/placement Python tasks MAY qualify. Exact Step,
    command, arguments, named reads/products, original ordered source/model inputs,
    fixed source/constructor AST and complete existing scanner closure MUST agree.
    Raw model membership MUST be observed without following aliases or reading its
    bytes. Generated terrain/rim/library/output bytes MUST remain unopened and cold
    tails uncreated. This MUST NOT execute scripts or grant tasks/repair/Finish.
    """
    from atelier import build,build_products,paths
    from atelier.build_v2.controller_client import _open_root
    checkout,output_root=Path(checkout),Path(output_root)
    if (type(step) is not build.Step or type(step.name) is not str or step.name not in ROLES
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout==Path(checkout.anchor) or output_root==Path(output_root.anchor)):
        raise UnsupportedBrinecoveData('foreign Step or anchors')
    try:fd=_open_root(checkout);os.close(fd)
    except OSError as error:raise UnsupportedBrinecoveData('checkout is not anchored') from error
    role=ROLES[step.name];game=checkout/'games/yorimichi';world=game/'world'
    script=checkout/role['script'];rim=output_root/'brinecove-data/final-rim.json'
    library=output_root/'digests/brinecove-source-library.json'
    if step.name=='world.brinecove.rim_data':
        produced=(output_root/'terrain/FarHills/final.npz',);output=rim
        arguments=('--source',str(produced[0]),'--output',str(output));needs=[];reads=['terrain.FarHills.final'];extra=()
    else:
        produced=(rim,library);output=output_root/'brinecove-data/placements.json'
        arguments=('--rim',str(rim),'--source-library',str(library),'--output',str(output))
        needs=['world.brinecove.sources'];reads=['brinecove.rim_data'];extra=(library,*_model_inputs(game/'assets/brinecove/models'))
    for path in (*produced,output):_output(path)
    defaults={'deferred_inputs':[],'after':[],'outputs':[],'heavy':False,'pool_roots':[],
        'explicit':False,'verify':None,'cutoff':False,'references':[],'cache':True,'audit':False,
        'optional_inputs':[],'queries':[],'toolchain':False,'batch':None,'cook_recovery':None,
        'checkpoint_previous_needs':None,'checkpoint_restore':None,'checkpoint_outputs':(),
        'candidate_scope':None,'replan':False,'controller':None}
    dynamic={'name','commands','inputs','about','products','needs','reads'}
    if (set(vars(step))-dynamic!=set(defaults)
            or any(type(vars(step)[n]) is not type(v) or vars(step)[n]!=v for n,v in defaults.items())
            or type(step.needs) is not list or any(type(x) is not str for x in step.needs) or step.needs!=needs
            or type(step.reads) is not list or any(type(x) is not str for x in step.reads) or step.reads!=reads
            or type(step.commands) is not list or len(step.commands)!=1):
        raise UnsupportedBrinecoveData('original data controls differ')
    command=step.commands[0]
    if (type(command) is not build.Python or set(vars(command))!={'script','args'}
            or type(command.script) is not type(script) or command.script!=script
            or type(command.args) is not tuple or any(type(x) is not str for x in command.args) or command.args!=arguments):
        raise UnsupportedBrinecoveData('original Python arguments differ')
    if type(step.products) is not list or len(step.products)!=1:
        raise UnsupportedBrinecoveData('original product differs')
    product=step.products[0]
    if (type(product) is not build_products.Product
            or set(vars(product))!={'name','paths','collection','bounds','optional_paths'}
            or type(product.name) is not str or product.name!=role['product']
            or type(product.paths) is not tuple or any(type(p) is not type(output) for p in product.paths)
            or product.paths!=(output,) or product.collection is not None or product.bounds is not None
            or type(product.optional_paths) is not tuple or product.optional_paths!=()):
        raise UnsupportedBrinecoveData('original product differs')
    code=tuple(checkout/name for name in role['code'])
    if (type(step.inputs) is not list or len(step.inputs)!=len(code)+len(extra)
            or any(type(p) is not type(script) for p in step.inputs) or tuple(step.inputs)!=(*code,*extra)):
        raise UnsupportedBrinecoveData('original ordered source/model input membership differs')
    for name,path in zip(role['code'],code):
        if _digest(_source(checkout,path))!=role['code'][name]:
            raise UnsupportedBrinecoveData('original source structure differs: '+name)
    constructor=ast.parse(_source(checkout,game/'brinecove_atomic_build.py'))
    functions=[n for n in constructor.body if isinstance(n,ast.FunctionDef) and n.name=='steps']
    if len(functions)!=1 or hashlib.sha256(ast.dump(functions[0],include_attributes=False).encode()).hexdigest()!=CONSTRUCTOR_AST:
        raise UnsupportedBrinecoveData('original data constructor differs')
    allowed=set(code)
    class Scanner(build._FastImportScanner.__bases__[0]):
        def resolve(self,root,parts):
            if root==paths.STUDIO:root=checkout/'platform/studio'
            elif root==paths.STUDIO/'atelier':root=checkout/'platform/studio/atelier'
            found=super().resolve(root,parts)
            for path in found:
                if path not in allowed:raise UnsupportedBrinecoveData('unknown source import candidate')
                _source(checkout,path)
            return found
    if tuple(Scanner().local_imports(script,(world,world/'regions')))!=code:
        raise UnsupportedBrinecoveData('existing scanner source closure differs')
    raw=tuple(p for p in step.inputs if p not in produced)
    return BrinecoveData(step.name,script,arguments,raw,produced,code,((product.name,(output,)),))
