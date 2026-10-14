"""Read a checkout with its own build client, including older legacy recipes.

The caller sends this source to a child interpreter with GAME set. Do not import the caller's
build package: fingerprints must use exactly the implementation that made the donor's stamps.
"""
from dataclasses import replace
import json
from pathlib import Path

from atelier import build, manifest


EXCLUDED = {'logs', 'stamps', 'remote-proof', '.state', '.reuse-in-progress.json', '.reuse-complete.json'}


def excluded(name):
    return name in EXCLUDED or name.startswith('.restore-') or name.endswith('.tmp')


def inspect_game(game):
    ctx = build.Context(game)
    raw_hash_path = build._hash_path
    tools, input_index = {}, None
    artifacts = [ctx.out.resolve()]
    if ctx.uproject:
        artifacts += [ctx.uproject.parent / 'Content', ctx.uproject.parent / 'Binaries']
    artifacts = [p.resolve() for p in artifacts]

    def portable_hash_path(digest, path, skip=True):
        path = Path(path)
        if path.is_file() or path.is_dir():
            return raw_hash_path(digest, path, skip)
        # Old clients hashed absolute missing paths. Compare portable keys, but still validate
        # the donor's actual fingerprint and write the target's actual fingerprint to its stamp.
        identity, name = path.resolve(), str(path.resolve())
        for root, label in ((ctx.out, '<build>'), (build.paths.REPO, '<repo>')):
            if identity.is_relative_to(root.resolve()):
                name = label + '/' + str(identity.relative_to(root.resolve()))
                break
        digest.update(b'missing:' + name.encode())

    def fingerprint(step, done):
        nonlocal input_index
        if hasattr(step, 'cache'):
            # Memory-only hints: read each source/tool file from disk once in this inspection,
            # then reuse it only while its identity and change metadata still match. Product
            # certification below always re-reads every output byte independently.
            if input_index is None:
                from atelier.build_hashes import HashIndex
                input_index = HashIndex()
            return build.fingerprint(step, done, index=input_index, tool_cache=tools)
        return build.fingerprint(step, done)

    def portable(step, done):
        build._hash_path = portable_hash_path
        try:
            return fingerprint(step, done)
        finally:
            build._hash_path = raw_hash_path

    def copied(path):
        path = Path(path).resolve()
        if path.is_relative_to(artifacts[0]):
            relative = path.relative_to(artifacts[0])
            return bool(relative.parts) and not excluded(relative.parts[0])
        if any(path.is_relative_to(root) for root in artifacts[1:]):
            return True
        plugins = (build.paths.REPO / 'platform/engine/Plugins').resolve()
        if path.is_relative_to(plugins):
            parts = path.relative_to(plugins).parts
            return 'Binaries' in parts and 'Intermediate' not in parts
        return False

    done, compared, sources, result = {}, {}, {}, []
    for step in build.order(build.load_recipe(game).steps(ctx), []):
        named = bool(getattr(step, 'products', ()) or getattr(step, 'reads', ()) or
                     getattr(step, 'references', ()))
        products, problem = {}, None
        if named:
            from atelier import build_products
            for product in step.products:
                roots = product.roots() if hasattr(product, 'roots') else product.paths
                if not all(copied(p) for p in roots):
                    raise ValueError(f'{step.name}: reuse cannot copy every declared product root')
            try:
                products = build_products.records(step)
            except (OSError, ValueError) as error:
                problem = str(error)
        value = fingerprint(step, done)
        verified = portable(step, compared)
        own = replace(step, inputs=[p for p in step.inputs if not copied(p)])
        source = portable(own, sources)
        sources[step.name] = source
        # A fresh checkout lacks products. Compare the source identity of each producer here;
        # the full byte identities are compared after copying, before any stamp is installed.
        for product in getattr(step, 'products', ()):
            sources['product:' + product.name] = source
        path = ctx.stamps / (step.name + '.json')
        stamp = json.loads(path.read_text()) if path.exists() else {}
        outputs_ok = all(Path(p).exists() for p in step.outputs)
        if getattr(step, 'verify', None):
            outputs_ok = outputs_ok and bool(step.verify())
        if named:
            outputs_ok = outputs_ok and problem is None and not build.missing_product_inputs(step)
        made = build.outputs_digest(step) if getattr(step, 'cutoff', False) and outputs_ok else None
        done[step.name], compared[step.name] = made or value, made or verified
        entry = dict(name=step.name, fingerprint=value, verified_fingerprint=verified,
                     source=source, stamp=stamp, outputs_ok=outputs_ok, made=made)
        if named:
            build_products.feed_results(done, products)
            build_products.feed_results(compared, products)
            entry.update(products=products, product_error=problem)
        result.append(entry)
    return dict(steps=result, engine=str(ctx.unreal_root.resolve()), project=ctx.uproject.stem,
                editor_target=manifest.game(game)['editor_target'],
                build_version=json.loads((ctx.unreal_root / 'Engine/Build/Build.version').read_text()))


if 'GAME' in globals():
    print(json.dumps(inspect_game(GAME)))
