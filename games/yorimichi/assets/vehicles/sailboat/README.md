# Sailboat

A forgiving shore-launched dinghy replaces kiteboarding. K (or Sailboat on phone)
launches beside an open shore/low dock. A/D or the left/right phone buttons steer.
W / Raise sail starts cruising; releasing it keeps the sail up. S / Lower sail
stops. There is no wind-angle penalty, tacking requirement, or upwind restriction.
K / Step ashore requires a nearby grounded, unobstructed landing. Back to spawn
and map travel always stow the boat. Menus, phone suspension and input timeout
stop propulsion.

The 3.8 × 1.55 m hull uses a swept hull box plus submerged ground probes. The
seated pose solves hips, feet and hands against animated boat/tiller transforms.
The boom remains rigid, cloth lowers onto it and flutters with pinned edges,
while the hull gently rocks and translucent foam fades with speed. Wind changes
only the visual side of the sail, never whether the player can travel.

`build.py` generates five meshes (2,024 triangles total).
`japan/run.sh sailboat` builds/imports them and the native module. Asset imports
are isolated from city content. `python3 japan/sailboat/qa.py SESSION` checks
native behavior and captures actual rear/side gameplay. Phone tests run separately
against the live stream. Generated outputs go to `japan/out/sailboat`.

Reference: `../docs/sailboat/reference.png`, generated with ImageGen using the
actual harbor and yellow-boy game stills. A single cream sail, ochre corner,
teal faceted hull and warm wooden cockpit carry the current art direction.
The model uses +X for bow; the stern-mounted rudder/tiller and forward mast follow
the sheet's orthographic views. The concept's hero view reverses those details.
