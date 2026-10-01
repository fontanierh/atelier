# Sailboat

A forgiving shore-launched dinghy, the way to the south-west island. It has a single cream sail with an ochre corner,
a teal faceted hull and a warm wooden cockpit.

## Controls

| Action | Keyboard | Phone |
| --- | --- | --- |
| Launch beside an open shore or a low dock | K | Sailboat |
| Steer | A / D | Left / right buttons |
| Raise the sail (it stays up when released) | W | Raise sail |
| Lower the sail and stop | S | Lower sail |
| Step ashore at a nearby grounded, unobstructed landing | K | Step ashore |

There is no wind-angle penalty, tacking or upwind restriction; the wind only changes which side the sail shows.
Back to spawn and map travel always stow the boat, and menus, phone suspension and input timeout stop it.

## Build and check

```sh
uv run atelier build yorimichi world.sailboat unreal.compile unreal.world
uv run atelier qa yorimichi sailboat SESSION
```

- `world.sailboat` ([`build.py`](build.py), Blender) builds `SB_Hull`, `SB_Sail`, `SB_Boom`, `SB_Rudder` and `SB_Wake`
  into `build/yorimichi/sailboat/`.
- `unreal.world` imports them with `unreal/Scripts/import_sailboat.py` and `sailboat_material.py`.
- The `sailboat` scenario runs the game's native sailboat checks and captures rear and side gameplay stills into
  `build/yorimichi/sailboat/SESSION/`.
- [`phone/sailboat-smoke.mjs`](../../../phone/sailboat-smoke.mjs) drives the streamed touch controls.

## Reference

- The model's +X is the bow; the tiller pivots at (-1.90, 0, 0.64) at the stern, and the mast stands forward.
- The 3.8 x 1.55 m hull collides as a swept box, with submerged ground probes (`USailboatComponent`).
- The seated pose solves the hips, feet and hands against the animated boat and tiller.
- The boom stays rigid; the cloth lowers onto it and flutters with pinned edges. The hull rocks gently and the
  translucent foam fades with speed.
