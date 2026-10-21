"""The explicit bounded browser scene's normal asset and staging dependencies."""

from pathlib import Path
import json
import shutil

from atelier import paths
from atelier.build import Call, Step, UnrealCompile, UnrealPackage, UnrealScript

GAME = Path(__file__).resolve().parent
SCRIPTS = GAME / "unreal/Scripts"
PARK = GAME / "world/regions/skatepark/park.json"


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
            "-AdditionalCookerOptions=-nullrhi",
            f"-ubtargs=-NoUBA -MaxParallelActions={self.workers} -NoDebugInfo",
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
    log.write("staged Browser/park.json, scene.json and Cairo portrait\n")


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
                ctx.uproject,
            ],
            needs=["skate.runtime"],
            explicit=True,
            heavy=True,
            outputs=[
                GAME / ("unreal/Binaries/HTML5/Yorimichi" + extension)
                for extension in (".wasm", ".js", ".target", ".html5link.json")
            ],
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
            ],
            inputs=[
                SCRIPTS / ("import_" + name + ".py")
                for name in ("footsteps", "combat_audio", "skate_audio")
            ],
            needs=["unreal.compile", "audio.footsteps", "audio.combat", "audio.skate"],
            explicit=True,
            heavy=True,
            about="the bounded scene's original footsteps, ambience and board audio",
        ),
        Step(
            "browser.data",
            [Call("stage_browser_scene", stage_scene)],
            inputs=[
                Path(__file__),
                PARK,
                GAME / "assets/characters/portraits/cairo.png",
            ],
            needs=["unreal.cairo_pawn"],
            explicit=True,
            outputs=[
                content / "Data/Browser/park.json",
                content / "Data/Browser/scene-source.json",
                content / "Data/cairo/portrait.png",
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
            explicit=True,
            heavy=True,
            outputs=[
                ctx.out
                / "browser/package/HTML5/Yorimichi/Binaries/HTML5/Yorimichi.html"
            ],
            about="cook and archive the bounded WebGPU scene using the already verified Wasm build",
        ),
    ]
