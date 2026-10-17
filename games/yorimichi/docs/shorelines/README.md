# Shoreline presentation source

This is the static presentation for [the shoreline proposal](../SHORELINES_PROPOSAL.md).

Publish assembled files under `build/yorimichi/shorelines/site/`: copy `index.html`, `review.html`, `style.css`, `app.js` and `review.js` to its
root and `sectors.json` to `assets/`. Copy the selected JPEGs and provenance JSON from
`games/yorimichi/assets/shorelines/concepts/` to `assets/`. The generated `assets/survey-map.png` and
`assets/survey.json` are retained with the proposal evidence under `build/yorimichi/shorelines/`; their survey
script is retained there too. They describe the source revision stated in the proposal, not subsequent terrain.

All asset references are relative, so the assembled site works below the machine's tailnet `/shorelines/` path.
The machine-local hosting copy is independent of the worktree and owned by the `com.atelier.shorelines.site`
LaunchAgent. Do not replace other tailnet routes. No game build, paid call, or public internet deployment is needed
to serve these already completed concepts.

Copy `review-status.json` to `assets/runtime-review.json` for the initial pending state. Once native checks finish,
replace that generated data with the captured revision, clearly scoped checks/limits, original screenshots, film
paths and evidence links. Runtime captures stay in build/archive/hosting storage; do not relabel a Sunburst as game
evidence. The survey map remains the original baseline and is identified as surveyed terrain.
