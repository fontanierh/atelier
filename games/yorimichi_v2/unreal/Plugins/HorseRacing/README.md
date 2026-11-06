# Yorimichi horse racing rules

`AtelierHorseRacing` is a game-owned plugin in `games/yorimichi/unreal/Plugins/HorseRacing`.
It contains Yorimichi's stateless seeded draws, continuous racing calendar, horse values and
breed inheritance. Rules stay separate from actors, UI and rendering assets. Race outcomes
and ownership services are separate integrations. The plugin/module names, exported APIs,
reflected type paths and automation test names remain unchanged by the ownership move.

`HRRandom` preserves the reference UTF-16 hash and JSON-string seed/tag keys. Use
`TryDraw` and `TryPickWeighted` when admitting external values: they reject invalid
bounds/weights without changing the output. Supported ranges and total weights are
1–`MAX_int32`, matching the returned integer type. The internal `Draw`/`PickWeighted`
convenience functions require validated arguments and fail explicitly on violation.

Unreal discovers the enabled plugin in the project's standard `Plugins` directory. The normal
game compile, cook and network identity cover its source and descriptor; verified reuse carries
its generated binaries as independent copies. Native regression
`Atelier.HorseRacing.Random` covers reference parity, string escaping, non-BMP text,
range/weight rejection and call-order independence. Native acceptance is required on
the integration head; enabling the module does not enable a racing service.

`HRClock` supplies the continuous calendar and race slots. Race days last two real
hours; seasons last twelve race days; Grand Prix dates are every third race day.
Horse age advances one year per real week. `TryScheduleAt` admits external times and
counts without mutating output on failure. Slot lookup uses a binary upper bound,
including exact floating-point boundaries. World catch-up and persistence are separate
rules/service responsibilities; the clock itself owns neither a world nor wall time.

`HRHorseTypes` defines reflected horse, gene-pair, injury, appearance and career values.
These are data structures, not validated saves or requests; boundary validation belongs
to persistence and the authoritative rules. Public structures are exported across module
boundaries. Allele and ability sums widen before arithmetic, so malformed values cannot
overflow before boundary validation. A gene-pair index is strictly 0 or 1.

`HRBreeds` implements the four-allele dominance table and deterministic founder/parent
inheritance from [the fork's rules PR](https://github.com/Polozer/atelier/pull/3).
`TryExpress` and `TryGenerate` reject malformed alleles without changing their output;
missing genes retain the reference Standard/founder behavior. Save migration, individual
mesh scaling and rendering are separate integrations. Native regression
`Atelier.HorseRacing.BreedInheritance` covers the complete table, reference draws, each
missing-parent side and rejection without partial writes.
