"""Fixed recipe worker: the existing C2/C5 loop with a frozen private project view."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys


def _sibling(name):
    spec = importlib.util.spec_from_file_location('atelier_recipe_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


python_worker = _sibling('python_worker')
recipe_job = _sibling('recipe_job')
recipe_node = _sibling('recipe_node')
recipe_media = _sibling('recipe_media')
PYTHON_VERSION = 'atelier-recipe-python-job-1'
BLENDER_VERSION = 'atelier-recipe-blender-job-1'


class RecipePlatform:
    def __init__(self, base, writes, parents, tools=None):
        self.base, self.writes, self.parents = base, writes, parents
        self.tools = tools or {}

    def __getattr__(self, name):
        return getattr(self.base, name)

    def executables(self):
        return [*self.base.executables(), *self.tools.get('executables', ())]

    def reads(self):
        roots, literals = self.base.reads()
        return [*roots, *self.tools.get('read_subpaths', ())], [*literals, *self.tools.get('read_literals', ())]

    def extra_rules(self):
        return [*self.base.extra_rules(), *self.tools.get('extra_rules', ()), '(allow file-write-create ' + ' '.join('(literal ' + python_worker._quote(path) + ')' for path in self.parents) + ')']

    def write_subpaths(self, job_dir):
        return [os.path.join(job_dir, 'output'), os.path.join(job_dir, recipe_job.RUNTIME, 'tmp'), *self.writes]


class RecipeWorker(python_worker.Worker):
    VERSION = PYTHON_VERSION

    def __init__(self, requests, responses, sandboxed, blender=None, node=None, ffmpeg=None, ffprobe=None):
        super().__init__(requests, responses, sandboxed)
        self.blender = blender
        self.node = node
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self.native = _sibling('blender_worker') if blender else None
        self.base_platform = self.native.BlenderPlatform(blender) if blender else python_worker.Platform()
        self.platform = self.base_platform
        if blender:
            self.VERSION = BLENDER_VERSION

    def prepare_job(self, job, job_dir):
        view, self.protected, writes = recipe_job.prepare_view(job, job_dir)
        self.parents = sorted({str(parent) for output in writes for parent in Path(output).parents if parent.is_relative_to(view)})
        tools = job['params']['recipe'].get('tools', [])
        self.node_config = None
        self.media_config = None
        permissions = None
        if len(tools) > 1:
            raise ValueError('a recipe has more than one fixed tool role')
        if tools and tools[0].get('kind') == 'node.frontend':
            if not self.node:
                raise ValueError('declared Node frontend requires its explicit execution locator')
            descriptor = tools[0]
            declared = set(job['code']) | set(job['params']['recipe']['paths'])
            if (set(descriptor) != {'kind', 'entry', 'sources'} or descriptor['entry'] not in descriptor['sources']
                    or len(descriptor['sources']) != 3 or len(set(descriptor['sources'])) != 3
                    or any(recipe_job.relative(name) not in declared for name in descriptor['sources'])):
                raise ValueError('nested Node source is not in frozen declared inputs/code')
            sdk = recipe_node.discover_node(self.node)
            permissions = recipe_node.permissions(sdk)
            self.node_config = {'sdk': sdk, 'view': str(view),
                'scratch': str(Path(job_dir) / recipe_job.RUNTIME / 'tmp'),
                'entry': str(view / descriptor['entry']), 'sources': [str(view / name) for name in descriptor['sources']],
                'source': Path(__file__).with_name('recipe_node.py').read_text(encoding='utf-8')}
        elif tools and tools[0].get('kind') == 'media.audio':
            descriptor = tools[0]
            paths = job['params']['recipe']['paths']
            def declared_media_input(name):
                name = recipe_job.relative(name)
                if name in paths:
                    return True
                root = view / name
                if not root.is_dir() or root.is_symlink():
                    return False
                files = [path for path in root.rglob('*') if not path.is_dir()]
                return bool(files) and all(path.is_file() and not path.is_symlink()
                    and str(path.relative_to(view)) in paths for path in files)
            if (set(descriptor) != {'kind', 'inputs', 'writes'} or not descriptor['inputs']
                    or any(not declared_media_input(name) for name in descriptor['inputs'])
                    or len(descriptor['writes']) != 1
                    or not recipe_job.relative(descriptor['writes'][0]).endswith('/audio/.tmp')):
                raise ValueError('audio source/temp roles are not in frozen declared inputs')
            sdk = recipe_media.discover_media(self.ffmpeg, self.ffprobe)
            permissions = recipe_media.permissions(sdk)
            writes = [*writes, *(str(view / name) for name in descriptor['writes'])]
            self.media_config = {'sdk': sdk, 'view': str(view),
                'scratch': str(Path(job_dir) / recipe_job.RUNTIME / 'tmp'),
                'inputs': [str(view / name) for name in descriptor['inputs']], 'writes': [str(path) for path in writes],
                'source': Path(__file__).with_name('recipe_media.py').read_text(encoding='utf-8')}
        elif tools:
            raise ValueError('unsupported nested recipe tool role')
        self.platform = RecipePlatform(self.base_platform, writes, self.parents, permissions)
        self.aliases = [str(Path(recipe_job.RUNTIME) / 'view' / name) for name in job['code']]
        self.view = view

    def configuration(self, job, job_dir, result_fd):
        config = super().configuration(job, job_dir, result_fd)
        config['code'] = [*config['code'], *self.aliases]
        config['working_directory'] = str(self.view)
        config['mkdir_existing'] = self.parents
        if self.node_config is not None:
            config['node_context'] = self.node_config
        if self.media_config is not None:
            config['media_context'] = self.media_config
        return config

    def child_command(self):
        if self.native:
            expression = f'{self.native.BOOTSTRAP}\n_main({python_worker.JOB_SOURCE!r})\n'
            return [self.blender, *self.native.JOB_FLAGS, '--python-expr', expression]
        return super().child_command()

    def child_environment(self, job_dir):
        environment = super().child_environment(job_dir)
        temporary = os.path.join(job_dir, recipe_job.RUNTIME, 'tmp')
        environment['TMPDIR'] = temporary
        if self.native:
            environment.update({name: os.path.join(temporary, 'user') for name in self.native.USER_FOLDERS})
        return environment


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    parser.add_argument('--request-fd', type=int, required=True)
    parser.add_argument('--response-fd', type=int, required=True)
    args = parser.parse_args(argv)
    for fd in (args.request_fd, args.response_fd):
        os.set_inheritable(fd, False)
    requests = os.fdopen(args.request_fd, 'rb', buffering=0)
    responses = os.fdopen(args.response_fd, 'wb', buffering=0)
    try:
        import bpy
    except ImportError:
        blender = None
    else:
        blender = bpy.app.binary_path
    RecipeWorker(requests, responses, True, blender, args.node, args.ffmpeg, args.ffprobe).serve()


if __name__ == '__main__':
    main()
