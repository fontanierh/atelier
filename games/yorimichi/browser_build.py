"""The explicit bounded browser scene's normal asset and staging dependencies."""

from pathlib import Path
import hashlib
import json
import shutil
import tempfile

from atelier import paths, build_products
from atelier.build import Call, Step, UnrealCompile, UnrealPackage, UnrealScript
from atelier.build_cook import options as cook_options

GAME = Path(__file__).resolve().parent
SCRIPTS = GAME / "unreal/Scripts"
PARK = GAME / "world/regions/skatepark/park.json"


def prepared_present(ctx):
    """A local compile stamp cannot admit an unprepared or stale Wasm module."""

    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    try:
        binary = GAME / "unreal/Binaries/HTML5/Yorimichi.wasm"
        report = json.loads(
            (ctx.out / "browser-float/Yorimichi/latest.json").read_text()
        )
        policy = hashlib.sha256()
        tools = paths.ENGINE_PLUGINS / "Activities/Skate/Tools"
        for name in ("prepare_wasm.py", "wasm_float.py", "wasm_float_helpers.py"):
            policy.update(name.encode() + b"\0")
            policy.update((tools / name).read_bytes().replace(b"\r\n", b"\n"))
        return (
            report["policy_sha256"] == policy.hexdigest()
            and report["output_sha256"] == digest(binary)
            and report["link_manifest_sha256"]
            == digest(binary.with_suffix(".html5link.json"))
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


class BrowserPackage(UnrealPackage):
    """Use the ordinary package guard/telemetry with the pinned fork's HTML5 UAT."""

    @property
    def env(self):
        return tuple(
            (name, str(self.workers))
            for name in ("DOTNET_PROCESSOR_COUNT", "EMCC_CORES", "BINARYEN_CORES")
        )

    def runs(self):
        return [Path(__file__), *super().runs()]

    def argv(self, ctx):
        cooker = [
            '-nullrhi', '-NoDefaultMaps',
            f'-DEFGameIni="{ctx.out / "browser/CookGame.ini"}"',
            f'-FOOBASEDIR="{ctx.out / "browser/file-open"}"',
        ]
        extra = []
        for option in cook_options(self.cook_mode, ctx.unreal_root):
            if option.startswith('-AdditionalCookerOptions='):
                cooker.append(option.split('=', 1)[1])
            else:
                extra.append(option)
        return [
            str(ctx.unreal_root / "Engine/Build/BatchFiles/RunUAT.sh"),
            "BuildCookRun",
            f"-project={ctx.uproject}",
            "-target=Yorimichi",
            "-platform=HTML5",
            f"-clientconfig={self.config}",
            "-skipbuild",
            "-nocompileeditor",
            f"-unrealexe={ctx.unreal_cmd}",
            "-cook",
            "-map=/Game/Browser/SkatePier",
            "-stage",
            "-pak",
            "-archive",
            f"-archivedirectory={self.archive}",
            "-noP4",
            "-unattended",
            "-utf8output",
            "-nodebuginfo",
            "-AdditionalCookerOptions=" + ' '.join(cooker),
            f"-ubtargs=-NoUBA -MaxParallelActions={self.workers} -NoDebugInfo",
            *extra,
        ]


def stage_scene(ctx, log):
    """Stage the committed park with an explicit bounded selection of scenery."""
    park = json.loads(PARK.read_text())
    # The first browser scene deliberately contains the riding geometry and
    # rails. The island's detailed perimeter foliage is a later measured chunk.
    park.pop("trees", None)
    root = paths.content_data(ctx.game) / "Browser"
    root.mkdir(parents=True, exist_ok=True)
    (root / "park.json").write_text(json.dumps(park, indent=2) + "\n")
    (root / "scene-source.json").write_text(
        json.dumps(
            {
                "version": 1,
                "profile": "skate-pier",
                "required_assets": [],
            },
            indent=2,
        )
        + "\n"
    )
    portrait = GAME / "assets/characters/portraits/cairo.png"
    shutil.copyfile(portrait, paths.content_data(ctx.game) / "cairo/portrait.png")
    # The cooker is a Mac editor process: its default Game config uses the host
    # packaging directories. Apply the target's bounded override explicitly,
    # while retaining the game's shared simulation/audio settings.
    config = ctx.out / 'browser/CookGame.ini'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text((GAME / 'unreal/Config/DefaultGame.ini').read_text() + '\n'
                      + (GAME / 'unreal/Config/HTML5/HTML5Game.ini').read_text())
    log.write("staged Browser/park.json, scene.json and Cairo portrait\n")


def audio_state(ctx):
    """@cc [owner:fontanierh,label:correctness] browser-audio-complete-proof
    Browser audio reuse MUST verify the complete manifest-defined source banks and imported
    packages, including sidecar membership and bytes. Missing, changed, linked, empty or
    mismatched banks MUST fail; a report or representative asset cannot prove a whole bank.
    """
    out, content = ctx.out, GAME / 'unreal/Content'
    sources, packages, roots = [], [], []
    for bank in ('footsteps', 'combat', 'skate'):
        source = out / 'audio' / bank
        manifest = source / 'manifest.json'
        data = json.loads(manifest.read_text())
        if bank == 'skate':
            if not isinstance(data, dict) or not isinstance(data.get('cues'), dict) or not all(isinstance(c, list) for c in data['cues'].values()):
                raise ValueError('Malformed skate audio manifest')
            rows = [row for cue in data['cues'].values() for row in cue]
        else:
            rows = data
        if not isinstance(rows, list) or not rows:
            raise ValueError('Empty audio bank: ' + bank)
        if any(not isinstance(row, dict) or not isinstance(row.get('file'), str) for row in rows):
            raise ValueError('Malformed audio manifest: ' + bank)
        waves = [source / row['file'] if bank == 'combat' else out / row['file'] for row in rows]
        actual = {p for p in source.glob('*/*.wav') if bank == 'skate' or p.parent.name != 'preview'}
        if len(set(waves)) != len(waves) or set(waves) != actual:
            raise ValueError('Prepared audio bank differs from its manifest: ' + bank)
        destination = content / ('Japan/Audio/Footsteps' if bank == 'footsteps' else 'Audio/' + bank.title())
        expected = {destination / (p.parent.name if bank == 'footsteps' else '') / (p.stem + '.uasset') for p in waves}
        if len(expected) != len(waves) or set(destination.rglob('*.uasset')) != expected:
            raise ValueError('Imported audio bank is incomplete or stale: ' + bank)
        sources.extend([manifest, *sorted(waves)])
        packages.extend(sorted(expected))
        roots.append(destination)
    footstep = [content / 'Japan/Audio' / name for name in ('DA_Footsteps.uasset', 'A_Footstep.uasset')]
    packages.extend(footstep)
    roots.extend(footstep)
    for path in [*sources, *packages, *roots]:
        anchor = out if path.is_relative_to(out) else content
        if any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(anchor)):
            raise ValueError('Linked audio input/output: ' + str(path))
    if any(not p.is_file() or p.stat().st_size == 0 for p in [*sources, *packages]):
        raise ValueError('Missing or empty audio source/package')
    sidecars = tuple(p.with_suffix(ext) for p in footstep for ext in ('.uexp', '.ubulk', '.uptnl'))
    return dict(
        schema=1,
        source_paths=[p.relative_to(out).as_posix() for p in sources],
        sources=build_products.inventory(build_products.Product('browser.audio.sources', tuple(sources))),
        packages=build_products.inventory(build_products.Product('browser.audio.packages', tuple(roots), optional_paths=sidecars)),
    )


def record_audio(ctx, log):
    state = audio_state(ctx)
    destination = ctx.out / 'browser/audio-import.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as stream:
        pending = Path(stream.name)
        try:
            json.dump(state, stream, sort_keys=True)
            stream.write('\n')
            stream.close()
            pending.replace(destination)
        finally:
            pending.unlink(missing_ok=True)
    log.write('Complete browser audio source/package inventory verified.\n')


def audio_present(ctx):
    receipt = ctx.out / 'browser/audio-import.json'
    try:
        return not receipt.is_symlink() and json.loads(receipt.read_text()) == audio_state(ctx)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def steps(ctx):
    content = GAME / "unreal/Content"
    return [
        Step(
            "browser.compile",
            [UnrealCompile("Yorimichi", platform="HTML5", args=("-NoDebugInfo",))],
            inputs=[
                GAME / "unreal/Source",
                GAME / "unreal/Config",
                GAME / "unreal/Plugins",
                paths.ENGINE_PLUGINS,
                ctx.uproject or GAME / 'unreal/Yorimichi.uproject',
            ],
            needs=["skate.runtime"],
            explicit=True,
            heavy=True,
            outputs=[
                GAME / ("unreal/Binaries/HTML5/Yorimichi" + extension)
                for extension in (".wasm", ".js", ".html", ".target", ".html5link.json")
            ],
            products=[build_products.Product('browser.binary', (GAME / 'unreal/Binaries/HTML5',))],
            verify=lambda: prepared_present(ctx),
            about="the complete Yorimichi Wasm module with verified scoped simulation arithmetic",
        ),
        Step(
            "browser.audio",
            [
                UnrealScript(
                    SCRIPTS / "import_footsteps.py", "FOOTSTEP IMPORT COMPLETE"
                ),
                UnrealScript(
                    SCRIPTS / "import_combat_audio.py", "COMBAT AUDIO IMPORT COMPLETE"
                ),
                UnrealScript(
                    SCRIPTS / "import_skate_audio.py", "SKATE AUDIO IMPORT COMPLETE"
                ),
                Call('record_browser_audio', record_audio),
            ],
            inputs=[Path(__file__), Path(build_products.__file__), *[
                SCRIPTS / ("import_" + name + ".py")
                for name in ("footsteps", "combat_audio", "skate_audio")
            ]],
            needs=["unreal.compile", "audio.footsteps", "audio.combat", "audio.skate"],
            reads=['audio.footsteps', 'audio.combat', 'audio.skate'],
            explicit=True,
            heavy=True,
            outputs=[ctx.out / 'browser/audio-import.json'],
            verify=lambda: audio_present(ctx),
            about="the bounded scene's original footsteps, ambience and board audio",
        ),
        Step(
            "browser.data",
            [Call("stage_browser_scene", stage_scene)],
            inputs=[
                Path(__file__),
                PARK,
                GAME / "assets/characters/portraits/cairo.png",
                GAME / 'unreal/Config/DefaultGame.ini',
                GAME / 'unreal/Config/HTML5/HTML5Game.ini',
            ],
            needs=["unreal.cairo_pawn"],
            explicit=True,
            outputs=[
                content / "Data/Browser/park.json",
                content / "Data/Browser/scene-source.json",
                content / "Data/cairo/portrait.png",
                ctx.out / 'browser/CookGame.ini',
            ],
            about="the explicit skate-pier scene manifest and bounded park data",
        ),
        Step(
            "browser.scene",
            [
                UnrealScript(
                    SCRIPTS / "browser_scene.py", "BROWSER SCENE IMPORT COMPLETE"
                )
            ],
            inputs=[SCRIPTS / "browser_scene.py", SCRIPTS / "setup_project.py"],
            needs=[
                "browser.data",
                "browser.audio",
                "unreal.skatepark",
                "unreal.skate_board",
                "unreal.skate_data",
            ],
            references=["materials.shared"],
            explicit=True,
            heavy=True,
            outputs=[
                content / "Browser/SkatePier.umap",
                content / "Data/Browser/scene.json",
            ],
            about="Cairo, the skate pier, rails, typed skating data, painterly look and original audio",
        ),
        Step(
            "browser.package",
            [BrowserPackage("Yorimichi", ctx.out / "browser/package")],
            inputs=[Path(__file__), GAME / "unreal/Config"],
            needs=["browser.compile", "browser.scene"],
            reads=['browser.binary', 'materials.shared'],
            explicit=True,
            heavy=True,
            outputs=[
                ctx.out
                / "browser/package/HTML5/Yorimichi/Binaries/HTML5/Yorimichi.html"
            ],
            about="cook and archive the bounded WebGPU scene using the already verified Wasm build",
        ),
    ]
