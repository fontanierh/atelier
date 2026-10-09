# Ski lab (experimental)

A physics prototype for freestyle skiing, small enough to tune in a browser before any of it moves into an Unreal
plugin. `sim.js` simulates one skier on a heightfield, `terrain.js` builds a terrain park, `app.js` draws it with
Three.js and reads the keyboard or a gamepad. Nothing here names a game; a terrain park on a volcano is the first
intended use.

```sh
python3 -m http.server -d platform/web/ski-lab 8871 --bind 127.0.0.1   # then open http://127.0.0.1:8871/
node --test platform/web/ski-lab/test_ski.mjs                         # also run by pytest (test_ski_lab.py)
```

## Model

Metres, seconds and kilograms, z up. The rider and the skis are one rigid body (75 kg) whose inertia moves between
standing and tucked. Body axes: x forward along the skis, y left, z up. The simulation steps at 600 Hz.

**Snow.** Each ski is sampled at seven points along its 1.75 m length. A point below the snow gets a spring-damper
normal force, a regularised Coulomb glide friction along its local tangent and a sideways grip that grows from
`flatGrip` (0.35, a flat ski skids) to `edgeGrip` (1.1) as the ski tips onto its edge. The edged ski's contact line
bends into an arc of radius `sidecutRadius × cos(edge)` (17 m sidecut): each point's tangent turns with its distance
from the boot. Carving is not scripted: when the body yaws at speed/radius, every point's velocity lines up with
its tangent and the skis stop slipping. Sideways slip past the grip limit is a skid; tipping onto the leading edge
while sliding sideways catches it, and the force at the feet trips the rider.

**Legs.** The boots sit `h` below the pelvis and move with the leg servo, which is speed and acceleration limited.
Flexing never pulls the skis off the snow; extending pushes the boots into it, so a crouch and a fast extension pop
the skier off the snow through the snow's own reaction. Extension stops pushing past `legForceMax` times body weight,
landings above `absorbStart` compress the legs, and after a landing they straighten slowly (only a pop extends fast).
Weight fore and aft moves the boots under the pelvis.

**Rider.** The stick asks for a turn and the rider leans into it: the balance controller rolls the body toward the
felt force of that turn, at a roll rate it can still stop, with a torque limited by how far the centre of pressure
reaches across the skis (`balanceReach` × load). The edge follows the lean, never leads it: angulation sets the edge
that carves the curvature the lean from plumb can stand on. At low speed or with the edges flat, a pivot torque
turns the skis against the snow. A hockey stop flattens and pivots the skis across the travel (with the grip
reduced while they swing), leans back against the slide and then sets the edges as hard as that lean holds.

**Air.** Nothing but the assists applies a torque in the air: angular momentum is conserved and the spin rate is
`I⁻¹L`, so tucking into a grab spins faster. Spins come from the takeoff: winding up (right stick) and releasing the
pop unwinds against the snow, with the skis flattened to pivot. Landing scores the air time, spin (to the nearest
180), flips and the longest grab; a crash within 0.7 s turns the trick into a bail. Touching the snow with the hip
or head sphere, or falling past 78° of roll, is a crash.

**Assists.** `balanceAssist` keeps the lean inside what the skis can hold at the current speed, `airAssist` levels
pitch and roll toward the slope below, `spinAssist` adds a small yaw torque in the air. All three at 0 is plain
physics; the page has sliders for them.

## Park

The base slope is 9°. Each jump is designed from the lip speeds it must work for: a parabolic in-run to a sharp
lip, a level table long enough that the slowest rider (`speeds[0]`) clears the knuckle, and a landing long enough
that the fastest (`speeds[1]`) still lands on it with 3 m to spare (`touchdown()` is the point-mass ballistic). Where
a landing ends below the slope the whole hill steps down there, so the run-out never climbs into a second kicker:
gentle decks between features, the vertical drop taken on the landings. A lane of rollers runs beside the jumps,
banks at the edges keep riders in, and the scenery puts the run on a volcano's upper flank.

## Checks

`test_ski.mjs` verifies the claims above: straight running and load, carving at the sidecut's curvature, staying up
in turns at speed, toppling when leaning hard at a standstill with no assist, a hockey stop, the pop, spin and tuck
with conserved angular momentum, every jump's speed window and a straight run that lands each jump on its landing.

## Next

Rails and boxes (the Skate plugin's rail subsystem fits), butters on ski flex, two independent skis, a half-pipe,
an active-ragdoll rider in Unreal on the Skate plugin's physical rider, and a native port of `sim.js` for the game.
