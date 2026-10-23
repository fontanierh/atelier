"""Reload a declared recipe after a completed geometry planner discovers atomic exports."""
REPLAN = 76  # Internal controller result; never a successful public build exit.


def execute(ctx, wanted, *, steps, force, touch, echo, index, max_heavy_commands):
    """@cc [owner:fontanierh,label:correctness] certified-planner-expansion
    Only a successfully completed planner MAY request recipe expansion. Its normal output,
    product, cache and checkpoint validation MUST finish before expansion. Reloaded exports
    MUST go through the ordinary build graph and current-input validation; previously completed
    work MUST retain its stamps and products. Heavy-command budgets MUST span all passes.
    Missing plans MUST never become a successful empty final assembly.
    """
    from . import build
    seen = set()
    ctx.expansion_heavy_commands = 0
    ctx.expansion_completed = {}
    try:
        while True:
            code = build._build(ctx, wanted, force=force, touch=touch, echo=echo, index=index,
                                steps=steps, max_heavy_commands=max_heavy_commands)
            if code != REPLAN:
                return code
            token = getattr(ctx, 'recipe_expansion', None)
            if token is None or token in seen:
                raise ValueError('Planner expansion repeated without a new completed result')
            seen.add(token)
            echo('Discovering independently cached exports after ' + token[0])
            steps = build.load_recipe(ctx.game).steps(ctx)
            build.check_modules(steps)
    finally:
        for field in ('expansion_completed', 'expansion_heavy_commands', 'recipe_expansion'):
            ctx.__dict__.pop(field, None)
