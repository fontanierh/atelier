"""Keep heavy jobs from hurting the machine: one big Unreal or Blender job at a time, optionally one small job beside it
(`render_lock`), a memory ceiling watched by a sibling process, 10 GiB by default or 4 GiB in the small slot (`memory_guard`,
`guard`), and the effective settings a run reports (`provenance.profile_from_log`). `guarded.run` combines them for any child process."""
