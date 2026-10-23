import contextlib, io, json, os, sys, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch

import pytest

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


    def test_outputs_count_in_any_folder(self):
        binaries = Path(self.temp.name) / 'out' / 'Binaries' / 'module.dylib'
        binaries.parent.mkdir(parents=True); binaries.write_bytes(b'1')
        step = Step('compile', [], outputs=[binaries.parent.parent], cutoff=True)
        before = builder.outputs_digest(step)
        binaries.write_bytes(b'2')
        self.assertNotEqual(builder.outputs_digest(step), before)


class DeclaredModuleTests(unittest.TestCase):
    def test_a_script_must_need_the_module_steps_it_declares(self):
        script = UnrealScript(Path('import.py'), 'DONE', modules=('Tools', 'Assets'))
        check_modules([Step('unreal.import', [script], needs=unreal_modules.needs(script.modules))])
        with self.assertRaises(SystemExit):
            check_modules([Step('unreal.import', [script], needs=['unreal.module.Tools'])])

    def test_a_plain_script_keeps_its_fingerprint(self):
        self.assertEqual(repr(UnrealScript(Path('import.py'), 'DONE')),
                         "UnrealScript(script=PosixPath('import.py'), marker='DONE', null_rhi=False, env=(), args=())")

    def test_changing_the_declared_modules_reruns_the_import(self):
        """Even when the step still needs both digests (another command uses them): the new boundary must run."""
        def step(modules):
            return Step('import', [UnrealScript(Path('import.py'), 'DONE', modules=modules)],
                        needs=['unreal.module.Tools', 'unreal.module.Assets'])
        done = {'unreal.module.Tools': 'outputs:tools', 'unreal.module.Assets': 'outputs:assets'}
        check_modules([step(('Tools', 'Assets')), step(('Tools',))])
        self.assertNotEqual(builder.fingerprint(step(('Tools', 'Assets')), done), builder.fingerprint(step(('Tools',)), done))

    def test_the_isolation_code_is_part_of_a_guarded_step_fingerprint(self):
        """The guard and the code that decides the descriptor: a revised isolation rule reruns the imports."""
        for index, original in enumerate(builder.ISOLATION):
            with tempfile.TemporaryDirectory() as temp:
                copy = Path(temp) / original.name
                copy.write_text(original.read_text())
                isolation = tuple(copy if i == index else path for i, path in enumerate(builder.ISOLATION))
                with patch.object(builder, 'ISOLATION', isolation):
                    guarded = Step('unreal.import', [UnrealScript(Path('import.py'), 'DONE', modules=('Tools',))])
                    plain = Step('unreal.import', [UnrealScript(Path('import.py'), 'DONE')])
                    before = builder.fingerprint(guarded, {}), builder.fingerprint(plain, {})
                    copy.write_text(copy.read_text() + '\n# changed\n')
                    self.assertNotEqual(builder.fingerprint(guarded, {}), before[0], original.name)
                    self.assertEqual(builder.fingerprint(plain, {}), before[1], original.name)

    def test_the_digest_implementation_is_part_of_its_step_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / 'unreal_modules.py'
            copy.write_text(Path(unreal_modules.__file__).read_text())
            ctx = types.SimpleNamespace(out=Path(temp) / 'out')
            with patch.object(unreal_modules, '__file__', str(copy)):
                fingerprint = lambda: builder.fingerprint(unreal_modules.steps(ctx, ['Tools'])[0], {'unreal.compile': 'same'})
                before = fingerprint()
                copy.write_text(copy.read_text().replace('hashlib.sha256', 'hashlib.sha512'))
                self.assertNotEqual(fingerprint(), before)


class ModuleDigestTests(unittest.TestCase):
    """A stand-in compiled project: Tools links the Kit plugin's module, whose plugin needs the Base plugin and has a
    second module (KitEditor) that nothing links, and a third that the editor target does not build; Game is unrelated;
    the engine's libraries are not the project's."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / 'Epic Games' / 'game'
        self.uproject = self.project / 'Game.uproject'
        self.write(self.uproject, json.dumps({'Modules': [{'Name': 'Game', 'Type': 'Runtime'}, {'Name': 'Tools', 'Type': 'Editor'}],
                                              'Plugins': [{'Name': 'Kit', 'Enabled': True}],
                                              'AdditionalPluginDirectories': ['../plugins']}))
        self.write(self.project.parent / 'plugins/Kit/Kit.uplugin', json.dumps({'Modules': [{'Name': 'Kit'}, {'Name': 'KitEditor'}, {'Name': 'KitProgram'}],
                                                                                'Plugins': [{'Name': 'Base', 'Enabled': True}]}))
        self.write(self.project.parent / 'plugins/Base/Base.uplugin', json.dumps({'Modules': [{'Name': 'Base'}]}))
        self.write(self.project.parent / 'plugins/Other/Other.uplugin', json.dumps({'Modules': [{'Name': 'Other'}]}))
        self.binaries = self.project / 'Binaries' / 'Mac'
        names = ('Tools', 'Game', 'Kit', 'KitEditor', 'Base', 'Other')
        self.write(self.binaries / 'UnrealEditor.modules', json.dumps({'BuildId': '1', 'Modules': {
            name: f'libUnrealEditor-{name}.dylib' for name in names}}))
        for name in names:
            self.write(self.library(name), f'{name} 1')
        self.config = self.project / 'Config' / 'DefaultGame.ini'
        self.write(self.config, '[/Script/Tools.Tool]\nSpeed=1\n')
        self.plugin_config = self.project.parent / 'plugins/Kit/Config/DefaultKit.ini'
        self.write(self.plugin_config, '[/Script/Kit.Kit]\nSize=1\n')
        self.write(self.project.parent / 'plugins/Other/Config/DefaultOther.ini', '[/Script/Other.Other]\nSize=1\n')
        self.loads = {'libUnrealEditor-Tools.dylib': ['libUnrealEditor-Kit.dylib', 'libUnrealEditor-Engine.dylib']}
        links = patch.object(unreal_modules, 'links', lambda library: self.loads.get(Path(library).name, []))
        links.start(); self.addCleanup(links.stop)
        owners = {'Tools': self.project / 'Source', 'Game': self.project / 'Source', 'Kit': self.project.parent / 'plugins/Kit/Source',
                  'KitEditor': self.project.parent / 'plugins/Kit/Source', 'Base': self.project.parent / 'plugins/Base/Source',
                  'Other': self.project.parent / 'plugins/Other/Source'}
        self.sources = {name: root / name for name, root in owners.items()}
        for name, folder in self.sources.items():
            self.write(folder / f'{name}.Build.cs', f'// {name} rules')
            self.write(folder / 'Private' / f'{name}.cpp', f'// {name} code')
        self.write(self.project / 'Source' / 'GameEditor.Target.cs', '// editor target rules')
        self.tools = {'engine': {'Engine/Build/Build.version': 'engine 1'}, 'toolchain': {'sdk': 'sdk 1'}}
        identity = patch.object(unreal_modules, 'tool_identity', lambda *a: self.tools)
        identity.start(); self.addCleanup(identity.stop)

    def library(self, name):
        return self.binaries / f'libUnrealEditor-{name}.dylib'

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

    def code(self):
        return unreal_modules.code(self.uproject, 'Tools')

    def test_closure_follows_links_and_whole_plugins(self):
        self.assertEqual(unreal_modules.closure(self.uproject, ['Tools']), {'Tools', 'Kit', 'KitEditor', 'Base'})
        self.assertEqual(unreal_modules.closure(self.uproject, ['Game']), {'Game'})

    def test_code_covers_the_closure_its_descriptors_and_config(self):
        modules = [f'<{name}>/{file}' for name in ('Base', 'Kit', 'KitEditor', 'Tools')
                   for file in (f'Private/{name}.cpp', f'{name}.Build.cs')]
        self.assertEqual(sorted(self.code()), sorted(['<Kit>/Config/DefaultKit.ini', '<config>/Config/DefaultGame.ini', 'Base.uplugin',
                                                      'Game.uproject', 'Kit.uplugin', '<targets>/GameEditor.Target.cs', '<tools>',
                                                      *modules]))

    def test_code_changes_with_compile_inputs_and_config_only(self):
        """Sources, build and target rules, descriptors and config of the closure count; library bytes do not."""
        before = self.code()
        for name in ('Tools', 'Kit', 'Game', 'Other'):
            self.write(self.library(name), f'{name} relinked elsewhere')  # Absolute paths make each build differ.
        self.write(self.sources['Game'] / 'Private/Game.cpp', '// unrelated edit')
        self.write(self.sources['Other'] / 'Private/Other.cpp', '// unrelated edit')
        self.write(self.project.parent / 'plugins/Other/Config/DefaultOther.ini', 'Size=2\n')
        self.assertEqual(self.code(), before)
        for path in (self.sources['Tools'] / 'Private/Tools.cpp', self.sources['Kit'] / 'Kit.Build.cs',
                     self.sources['KitEditor'] / 'Private/KitEditor.cpp', self.sources['Base'] / 'Private/Base.cpp',
                     self.project / 'Source/GameEditor.Target.cs', self.config, self.plugin_config, self.uproject):
            text = path.read_text()
            self.write(path, text + ' ')
            self.assertNotEqual(self.code(), before, path.name)
            self.write(path, text)
        self.assertEqual(self.code(), before)

    def test_same_sources_in_another_checkout_path_give_the_same_digest(self):
        import shutil
        before = self.code()
        other = Path(self.temp.name) / 'a much longer checkout path' / 'Epic Games'
        shutil.copytree(self.project.parent, other)
        for library in (other / 'game/Binaries/Mac').glob('*.dylib'):
            library.write_text(library.read_text() + ' built at ' + str(other))
        self.assertEqual(unreal_modules.code(other / 'game/Game.uproject', 'Tools'), before)

    def test_engine_or_toolchain_changes_change_the_digest(self):
        before = self.code()
        self.tools = {**self.tools, 'engine': {'Engine/Build/Build.version': 'engine 2'}}
        self.assertNotEqual(self.code(), before)
        self.tools = {**self.tools, 'engine': {'Engine/Build/Build.version': 'engine 1'}, 'toolchain': {'sdk': 'sdk 2'}}
        self.assertNotEqual(self.code(), before)

    def test_a_prebuilt_module_without_sources_keys_on_its_library(self):
        import shutil
        shutil.rmtree(self.sources['Base'])
        before = self.code()
        self.assertIn('libUnrealEditor-Base.dylib', before)
        self.write(self.library('Base'), 'Base 2')
        self.assertNotEqual(self.code(), before)

    def test_record_writes_a_stable_digest(self):
        output = Path(self.temp.name) / 'digest.json'
        first = unreal_modules.record(self.uproject, 'Tools', output)
        text = output.read_text()
        self.assertEqual(unreal_modules.record(self.uproject, 'Tools', output), first)
        self.assertEqual(output.read_text(), text)

    def test_a_module_that_was_not_compiled_is_an_error(self):
        with self.assertRaises(SystemExit):
            unreal_modules.code(self.uproject, 'Missing')
        self.library('Kit').unlink()
        with self.assertRaises(SystemExit):
            self.code()

    def test_the_descriptor_loads_only_the_closure(self):
        with unreal_modules.descriptor(self.uproject, ['Tools']) as (path, left_out):
            self.assertEqual(path.parent, self.project)
            contents = json.loads(path.read_text())
            self.assertEqual([m['Name'] for m in contents['Modules']], ['Tools'])
            self.assertEqual(contents['Plugins'], [{'Name': 'Kit', 'Enabled': True}, {'Name': 'Other', 'Enabled': False}])
            self.assertEqual([Path(p).name for p in left_out], ['libUnrealEditor-Game.dylib', 'libUnrealEditor-Other.dylib'])
        with unreal_modules.descriptor(self.uproject, ['Tools']) as (again, _):
            self.assertEqual(again, path)        # the same project name on every run
        with unreal_modules.descriptor(self.uproject, ['Game']) as (other, _):
            self.assertNotEqual(other, path)

    def test_the_descriptor_exists_only_for_its_run(self):
        with unreal_modules.descriptor(self.uproject, ['Tools']) as (path, _):
            self.assertTrue(path.is_file())
        self.assertFalse(path.exists())
        with self.assertRaises(RuntimeError), unreal_modules.descriptor(self.uproject, ['Tools']):
            raise RuntimeError('the editor failed')
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['Binaries', 'Config', 'Game.uproject', 'Source'])

    def test_a_guarded_run_removes_its_descriptor_whatever_the_outcome(self):
        """Success, a failed editor and a refused render slot all end with the project folder as it was."""
        ctx = types.SimpleNamespace(uproject=self.uproject, unreal_cmd='UnrealEditor-Cmd', logs=Path(self.temp.name) / 'logs',
                                    game='game', out=(Path(self.temp.name) / 'out').resolve(), env=lambda extra: dict(extra))
        command = UnrealScript(Path(self.temp.name) / 'import.py', 'IMPORTED', modules=('Tools',))
        step = Step('import', [command], heavy=True)
        seen = []

        def editor(code):
            def run(argv, folder, **kwargs):
                seen.append(Path(argv[1]).is_file())
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'stdout.log').write_text('IMPORTED')
                if code is None:
                    raise RuntimeError('render slot refused')
                return code
            return run
        for code, error in ((0, None), (1, 'exited 1'), (None, 'refused')):
            with patch.object(builder.guarded, 'run', editor(code)), patch.object(builder, 'slot_request', lambda ctx, step: ('job', None)):
                if error:
                    with self.assertRaisesRegex(RuntimeError, error):
                        builder.run_command(ctx, step, command, io.StringIO())
                else:
                    builder.run_command(ctx, step, command, io.StringIO())
            self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['Binaries', 'Config', 'Game.uproject', 'Source'])
        self.assertEqual(seen, [True, True, True])


class GuardTests(unittest.TestCase):
    def test_only_left_out_libraries_count(self):
        with tempfile.TemporaryDirectory() as temp:
            game, tools = Path(temp) / 'libUnrealEditor-Game.dylib', Path(temp) / 'libUnrealEditor-Tools.dylib'
            game.write_text(''); tools.write_text('')
            alias = Path(temp) / 'alias.dylib'; alias.symlink_to(game)
            self.assertEqual(guard.undeclared([str(tools), '/engine/libUnrealEditor-Engine.dylib'], [str(game)]), [])
            self.assertEqual(guard.undeclared([str(alias)], [str(game)]), [os.path.realpath(game)])

    @pytest.mark.macos_only  # dyld's image list is the only source of loaded libraries.
    def test_this_process_libraries_are_listed(self):
        self.assertTrue(any('python' in path.lower() or 'libsystem' in path.lower() for path in guard.loaded_libraries()))

    def test_the_check_runs_even_when_the_script_exits(self):
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / 'import.py'
            script.write_text('import sys\nsys.exit(0)\n')
            stops, checks = [], iter([[], ['/game/libUnrealEditor-Game.dylib']])
            with patch.object(guard, 'loaded_libraries', lambda: next(checks)), patch.object(guard, 'stop', stops.append), \
                    patch.dict(os.environ, ATELIER_SCRIPT=str(script), ATELIER_LEFT_OUT=json.dumps(['/game/libUnrealEditor-Game.dylib'])), \
                    patch.object(sys, 'argv', list(sys.argv)), patch.object(sys, 'path', list(sys.path)):
                with self.assertRaises(SystemExit):
                    guard.main()
        self.assertEqual(len(stops), 1)
        self.assertIn('libUnrealEditor-Game.dylib', stops[0])


if __name__ == '__main__':
    unittest.main()
