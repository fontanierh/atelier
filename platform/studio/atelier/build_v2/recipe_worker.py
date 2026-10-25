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
PYTHON_VERSION = 'atelier-recipe-python-job-1'
BLENDER_VERSION = 'atelier-recipe-blender-job-1'


class RecipePlatform:
    def __init__(self, base, writes, parents):
        self.base, self.writes, self.parents = base, writes, parents

    def __getattr__(self, name):
        return getattr(self.base, name)

    def extra_rules(self):
        return [*self.base.extra_rules(), '(allow file-write-create ' + ' '.join('(literal ' + python_worker._quote(path) + ')' for path in self.parents) + ')']

    def write_subpaths(self, job_dir):
        return [os.path.join(job_dir, 'output'), os.path.join(job_dir, recipe_job.RUNTIME, 'tmp'), *self.writes]


class RecipeWorker(python_worker.Worker):
    VERSION = PYTHON_VERSION

    def __init__(self, requests, responses, sandboxed, blender=None):
        super().__init__(requests, responses, sandboxed)
        self.blender = blender
        self.native = _sibling('blender_worker') if blender else None
        self.base_platform = self.native.BlenderPlatform(blender) if blender else python_worker.Platform()
        self.platform = self.base_platform
        if blender:
            self.VERSION = BLENDER_VERSION

    def prepare_job(self, job, job_dir):
        view, self.protected, writes = recipe_job.prepare_view(job, job_dir)
        self.parents = sorted({str(parent) for output in writes for parent in Path(output).parents if parent.is_relative_to(view)})
        self.platform = RecipePlatform(self.base_platform, writes, self.parents)
        self.aliases = [str(Path(recipe_job.RUNTIME) / 'view' / name) for name in job['code']]
        self.view = view

    def configuration(self, job, job_dir, result_fd):
        config = super().configuration(job, job_dir, result_fd)
        config['code'] = [*config['code'], *self.aliases]
        config['working_directory'] = str(self.view)
        config['mkdir_existing'] = self.parents
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
    RecipeWorker(requests, responses, True, blender).serve()


if __name__ == '__main__':
    main()
