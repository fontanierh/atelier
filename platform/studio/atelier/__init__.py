"""Atelier studio: the tools behind the `atelier` command.

The modules at this level (`paths`, `env`, `conventions`, `manifest`) use only the standard library, so they can be
imported from the command line, from Blender's Python and from Unreal's. Host-specific code lives in
`atelier.blender` and is only imported inside Blender.
"""
__version__ = '0.1.0'
