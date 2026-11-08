"""Native-ridden mega-ramp profiles, in additions semantics (plan metres).

The standalone modules were ridden with the gameplay Session follower at 1, 4
and 8 m/s starts on a native-y=100 crest. Both floor edges had curved 3 m
shoulders. This evidence sizes the modules; each assembled and rotated route
must still be ridden, including every downstream turn and bowl transfer.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Mega:
    name: str
    drop: float
    lip: float
    gap: float
    knuckle_drop: float
    landing: float
    min_air: float

    @property
    def rollin(self):
        """A preferred R80 crest and R60 foot, finishing at -5 degrees."""
        rise = 80. * (1 - math.cos(math.radians(35.))) + 60. * (
            math.cos(math.radians(5.)) - math.cos(math.radians(35.)))
        length = (self.drop - rise) / math.tan(math.radians(35.))
        return (('line', 2.), ('arc', 80., -35.), ('line', length), ('arc', 60., -5.))

    @property
    def approach(self):
        return (*self.rollin, ('line', 20.), ('arc', 30., self.lip), ('line', 3.))

    @property
    def receiver(self):
        return (('arc', 20., -self.landing), ('line', 34.), ('arc', 80., -5.),
                ('line', 25.), ('arc', 80., 0.), ('line', 35.))

    @property
    def rising_receiver(self):
        """A native-ridden receiver reclaiming height before the next turn.

        At 1/4/8 m/s tower starts, Orange exits at 25.63..26.17 m/s and
        Standard at 22.95..24.34 m/s. All six runs retain their required airs,
        on-slope landings and the hard 7 m/s peak normal-impact limit.
        """
        return (('arc', 20., -self.landing), ('line', 18.), ('arc', 60., 25.),
                ('line', 12.), ('arc', 80., 0.), ('line', 12.))

    @property
    def profile(self):
        return (*self.approach, ('gap', self.gap, -self.knuckle_drop, self.name), *self.receiver)


# Selected from actual native runs with the 7 m/s pre-contact peak impact gate.
# Orange: 63.09..68.29 m air, 8.75..13.98 m touchdown margin, peak 4.59..5.54 m/s.
# Standard: 51.80..54.06 m air, 10.46..12.73 m margin, peak 3.02..3.18 m/s.
ORANGE = Mega('L1 mega', drop=54., lip=18., gap=55., knuckle_drop=6., landing=24., min_air=60.)
STANDARD = Mega('mega', drop=48., lip=16., gap=42., knuckle_drop=4., landing=26., min_air=50.)
