import contextlib, io, json, os, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch

from atelier import build as builder, paths, unreal_modules, unreal_script_guard as guard
from atelier.build import Call, Step, UnrealScript, check_modules


class CutoffTests(unittest.TestCase):
    """A cutoff step that reruns and makes the same outputs leaves its dependents current."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'games' / 'standin').mkdir(parents=True)
        self.source, self.output = root / 'source.txt', root / 'out' / 'digest.txt'
        self.source.write_text('a')
        self.made, self.runs = 'digest 1', []

        def make(ctx, log):
            self.output.parent.mkdir(exist_ok=True); self.output.write_text(self.made); self.runs.append('digest')

        def use(ctx, log):
            self.runs.append('import')
        self.steps = [Step('digest', [Call('make', make)], inputs=[self.source], outputs=[self.output], cutoff=True),
                      Step('import', [Call('use', use)], needs=['digest'])]
        self.enter(patch.object(paths, 'GAMES', root / 'games'))
        self.enter(patch.object(builder, 'load_recipe', lambda game: types.SimpleNamespace(steps=lambda ctx: self.steps)))
        self.enter(patch.dict(os.environ, ATELIER_BUILD_ROOT=str(root / 'build')))

    def enter(self, context):
        context.start(); self.addCleanup(context.stop)

    def run_build(self, *wanted):
        self.runs = []
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.build('standin', wanted, echo=lambda line: None), 0)
        return self.runs

    def test_dependents_rerun_only_when_the_outputs_change(self):
        self.assertEqual(self.run_build(), ['digest', 'import'])
        self.assertEqual(self.run_build(), [])
        self.source.write_text('b')                      # the step reruns and makes the same digest
        self.assertEqual(self.run_build(), ['digest'])
        self.source.write_text('c'); self.made = 'digest 2'
        self.assertEqual(self.run_build(), ['digest', 'import'])

    def test_a_dependent_built_alone_sees_the_recorded_outputs(self):
        self.run_build()
        self.assertEqual(self.run_build('import'), [])
        self.made = 'digest 2'
        self.source.write_text('b')
        self.assertEqual(self.run_build('digest'), ['digest'])
        self.assertEqual(self.run_build('import'), ['import'])


class DeclaredModuleTests(unittest.TestCase):
    def test_a_script_must_need_the_module_steps_it_declares(self):
        script = UnrealScript(Path('import.py'), 'DONE', modules=(('Tools', 'code'), ('Game', 'interface')))
        check_modules([Step('unreal.import', [script], needs=unreal_modules.needs(script.modules))])
        with self.assertRaises(SystemExit):
            check_modules([Step('unreal.import', [script], needs=['unreal.module.Tools.code'])])

    def test_declared_modules_do_not_change_a_command_fingerprint(self):
        plain = UnrealScript(Path('import.py'), 'DONE')
        declared = UnrealScript(Path('import.py'), 'DONE', modules=(('Tools', 'code'),))
        self.assertEqual(repr(plain), repr(declared))


class ModuleDigestTests(unittest.TestCase):
    """A stand-in project: Tools links the Kit plugin module; Game is unrelated; the engine is outside the repository."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'; self.engine = Path(self.temp.name) / 'Epic Games' / 'engine'   # .d files escape the space
        self.project = self.repo / 'game'
        binaries = self.project / 'Binaries' / 'Mac'
        binaries.mkdir(parents=True)
        (binaries / 'UnrealEditor.modules').write_text(json.dumps({'BuildId': '1', 'Modules': {
            'Tools': 'libUnrealEditor-Tools.dylib', 'Game': 'libUnrealEditor-Game.dylib', 'Kit': 'libUnrealEditor-Kit.dylib'}}))
        self.files = {}
        for name in ('game/Source/Tools/Tool.cpp', 'game/Source/Tools/Tool.h', 'game/Source/Game/Game.cpp', 'plugins/Kit/Kit.h'):
            self.write(self.repo / name, f'// {name}\n')
        self.write(self.engine / 'Engine.h', 'engine\n')
        uht = self.project / 'Intermediate' / 'Build' / 'Mac' / 'UnrealEditor' / 'Inc' / 'Tools' / 'UHT'
        self.generated = uht / 'Tool.generated.h'
        self.write(self.generated, '#define FID_repo_game_Source_Tools_Tool_h_12_GENERATED_BODY\nUPROPERTY Speed\n')
        self.write(uht / 'Tool.gen.cpp', 'CONSTRUCT_RELOAD_VERSION_INFO(FClassReloadVersionInfo, sizeof(UTool), 123U)\n')
        tools = self.objects('Build', 'Tools')
        escaped = str(self.engine).replace(' ', '\\ ')
        self.write(tools / 'Tool.cpp.d', f'{tools}/Tool.cpp.o: \\\n  {self.repo}/game/Source/Tools/Tool.cpp \\\n'
                   f'  {self.repo}/game/Source/Tools/Tool.h {escaped}/Engine.h Runtime/Core.h \\\n  {self.generated} {uht}/Tool.gen.cpp\n')
        self.write(tools / 'Definitions.Tools.h', '#define TOOLS_API\n')
        self.write(tools / 'libUnrealEditor-Tools.dylib.rsp', f'"{binaries}/libUnrealEditor-Kit.dylib"\n"../Binaries/Mac/libUnrealEditor-Engine.dylib"\n')
        kit = self.objects('External/Build', 'Kit')
        self.write(kit / 'Kit.cpp.d', f'{kit}/Kit.cpp.o: {self.repo}/plugins/Kit/Kit.h\n')
        game = self.objects('Build', 'Game')
        self.write(game / 'Game.cpp.d', f'{game}/Game.cpp.o: {self.repo}/game/Source/Game/Game.cpp\n')

    def objects(self, folder, module):
        return self.project / 'Intermediate' / folder / 'Mac' / 'arm64' / 'UnrealEditor' / 'Development' / module

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

    def code(self):
        return unreal_modules.code(self.project, 'Tools', repo=self.repo, unreal_root=self.engine)

    def test_code_covers_the_module_and_the_modules_it_links_but_not_the_engine(self):
        self.assertEqual(sorted(self.code()), ['<Tools>/Definitions.Tools.h', 'game/Source/Tools/Tool.cpp',
                                               'game/Source/Tools/Tool.h', 'plugins/Kit/Kit.h'])

    def test_code_changes_with_its_sources_only(self):
        before = self.code()
        self.write(self.repo / 'game/Source/Game/Game.cpp', '// another edit\n')
        self.write(self.engine / 'Engine.h', 'engine 2\n')
        self.assertEqual(self.code(), before)
        self.write(self.repo / 'plugins/Kit/Kit.h', '// changed\n')
        self.assertNotEqual(self.code(), before)

    def test_interface_ignores_paths_lines_and_reload_checksums(self):
        before = unreal_modules.interface(self.project, 'Tools')
        self.write(self.generated, '#define FID_other_checkout_Source_Tools_Tool_h_40_GENERATED_BODY\nUPROPERTY Speed\n')
        self.write(self.generated.with_name('Tool.gen.cpp'), 'CONSTRUCT_RELOAD_VERSION_INFO(FClassReloadVersionInfo, sizeof(UTool), 987U)\n')
        self.assertEqual(unreal_modules.interface(self.project, 'Tools'), before)
        self.write(self.generated, '#define FID_other_checkout_Source_Tools_Tool_h_40_GENERATED_BODY\nUPROPERTY TopSpeed\n')
        self.assertNotEqual(unreal_modules.interface(self.project, 'Tools'), before)

    def test_record_writes_a_stable_digest(self):
        output = Path(self.temp.name) / 'digest.json'
        with patch.object(paths, 'REPO', self.repo):
            first = unreal_modules.record(self.project, 'Tools', 'code', output)
            text = output.read_text()
            self.assertEqual(unreal_modules.record(self.project, 'Tools', 'code', output), first)
        self.assertEqual(output.read_text(), text)

    def test_a_module_that_was_not_compiled_is_an_error(self):
        with self.assertRaises(SystemExit):
            unreal_modules.code(self.project, 'Missing', repo=self.repo, unreal_root=self.engine)


class Package:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path


def unreal_type(name, package):
    """A stand-in for a generated unreal type."""
    cls = type(name, (), {'__module__': 'unreal'})
    cls.static_class = classmethod(lambda c: types.SimpleNamespace(get_outer=lambda: Package(package)))
    return cls


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.Mesh = unreal_type('StaticMesh', '/Script/Engine')
        self.Tool = unreal_type('ToolLibrary', '/Script/Tools')
        self.Actor = unreal_type('ParkActor', '/Script/Game')
        self.Other = unreal_type('OtherThing', '/Script/Other')
        self.unreal = types.SimpleNamespace(StaticMesh=self.Mesh, ToolLibrary=self.Tool, ParkActor=self.Actor, OtherThing=self.Other,
                                            log=print)
        self.stops = []
        self.guard = guard.Guard(self.unreal, 'import.py', {'Tools': 'code', 'Game': 'interface'}, ['Tools', 'Game', 'Other'],
                                 self.stops.append)

    def test_names_from_undeclared_game_modules_stop_the_script(self):
        for name in ('StaticMesh', 'ToolLibrary', 'ParkActor', 'log'):
            self.guard.name(name)
        self.assertEqual(self.stops, [])
        self.guard.name('OtherThing')
        self.assertEqual(len(self.stops), 1)
        self.assertIn('Other', self.stops[0])

    def test_only_functions_of_modules_declared_by_code_run(self):
        self.Tool.run = classmethod(lambda cls: 'ran')
        self.Actor.place = lambda self: 'placed'
        self.Actor.speed = property(lambda self: 3)
        self.Mesh.build = lambda self: 'built'
        self.Other.helper = staticmethod(lambda: 'helped')
        restore = self.guard.seal()
        self.assertEqual((self.Tool.run(), self.Mesh().build(), self.Actor().speed), ('ran', 'built', 3))
        self.assertEqual(self.stops, [])
        self.Actor().place()
        self.Other.helper()
        self.assertEqual(len(self.stops), 2)
        self.assertIn('ParkActor.place from the game module Game, which its build step declares only by interface', self.stops[0])
        self.assertIn('not at all', self.stops[1])
        restore()
        self.assertEqual((self.Actor().place(), self.Other.helper()), ('placed', 'helped'))

    def test_functions_engine_types_define_stay_free_on_game_types(self):
        self.Mesh.set_editor_property = lambda self, name, value: 'set'
        World = type('ParkWorld', (self.Mesh,), {'__module__': 'unreal'})
        World.static_class = classmethod(lambda c: types.SimpleNamespace(get_outer=lambda: Package('/Script/Game')))
        self.unreal.ParkWorld = World
        self.guard.seal()
        self.assertEqual(World().set_editor_property('speed', 1), 'set')
        self.assertEqual(self.stops, [])


if __name__ == '__main__':
    unittest.main()
