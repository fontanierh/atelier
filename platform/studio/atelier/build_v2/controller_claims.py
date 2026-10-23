"""Exact declared controller files excluded from legacy artifact authority."""
from dataclasses import dataclass

from atelier import paths
from .controller_recipe import _claim


@dataclass(frozen=True)
class ControllerClaims:
    files: tuple = ()
    units: tuple = ()

    @classmethod
    def from_steps(cls, steps, checkout):
        from .controller_recipe import validate_markers
        steps = tuple(steps)
        validate_markers(steps, checkout)
        return cls(tuple(_claim(path) for step in steps if step.controller is not None
                         for path in step.controller.outputs(checkout)),
                   tuple(step.name for step in steps if step.controller is not None))

    def excludes(self, path):
        """Workspace membership excludes exact owned files, never their shared parents."""
        value = _claim(path)
        return any(value == owned or value.startswith(owned + '/') for owned in self.files)

    def refuse_overlap(self, paths):
        """@cc [owner:fontanierh,label:safety] controller-files-outside-legacy-authority
        Legacy receiving/destructive roots and complete candidate inventories MUST refuse
        exact, ancestor and normalized alias overlaps with actual declared controller files.
        Broad install permissions MUST NOT create claims. Other disjoint artifacts, including
        derived packages, MUST remain eligible. Workspace scans exclude owned files only,
        not their shared parent directories. See test_build_v2_controller_claims.py.
        """
        for path in paths:
            value = _claim(path)
            if any(value == owned or value.startswith(owned + '/') or owned.startswith(value + '/')
                   for owned in self.files):
                raise ValueError('legacy artifact authority overlaps a controller-owned file')

    def legacy_members(self, checkout, out, game):
        """Map the initial fixed-file scope to existing legacy labels, without output IO."""
        roots = ((_claim(out), 'generated'),
                 (_claim(checkout / 'games' / game / 'unreal/Content'), 'content'))
        members = []
        for path in self.files:
            matches = [(root, label) for root, label in roots if path.startswith(root + '/')]
            if len(matches) != 1:
                raise ValueError('controller retention file has unsupported legacy root mapping')
            root, label = matches[0]
            members.append(_claim('/' + label + path[len(root):]))
        return ControllerClaims(tuple(members), self.units)


def for_context(ctx):
    """Derive custody from the current normal recipe, without runtime Context or store opens."""
    cached = ctx.__dict__.get('_controller_file_claims')
    if cached is not None:
        return cached
    from .controller_entry import discover, declaration_context
    try:
        candidates = discover(ctx.game)
    except FileNotFoundError:
        candidates = {}
    if not candidates:
        result = ControllerClaims()
    else:
        from atelier import build
        steps = build.load_recipe(ctx.game).steps(declaration_context(ctx.game))
        build.check_declarations(steps)
        actual = {step.name: step.controller for step in steps if step.controller is not None}
        if (actual.keys() != candidates.keys()
                or any(actual[name].request(paths.REPO) != marker.request(paths.REPO)
                       for name, marker in candidates.items())):
            raise ValueError('normal recipe and controller ownership declarations disagree')
        result = ControllerClaims.from_steps(steps, paths.REPO)
    ctx.__dict__['_controller_file_claims'] = result
    return result


def for_source(checkout, game):
    """Retention reads current declaration metadata only; never payloads or certificates."""
    from .controller_entry import discover
    markers = discover(game, checkout=checkout)
    return ControllerClaims(tuple(_claim(path) for marker in markers.values()
                                  for path in marker.outputs(checkout)), tuple(markers))
