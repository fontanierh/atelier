"""Keep heavy jobs from hurting the machine: one big Unreal or Blender job at a time, optionally one small job beside it
(`render_lock`), a memory ceiling watched by a sibling process, 10 GiB or 4 GiB in the small slot (`memory_guard`,
`guard`), and a record of what ran (`provenance`). `guarded.run` combines them for any child process."""
