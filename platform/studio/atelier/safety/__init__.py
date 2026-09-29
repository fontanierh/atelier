"""Keep heavy jobs from hurting the machine: one Unreal or Blender render at a time (`render_lock`), a 10 GiB memory
ceiling watched by a sibling process (`memory_guard`, `guard`), and a record of what ran (`provenance`).
`guarded.run` combines them for any child process."""
