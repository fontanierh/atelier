"""Explicit constructor stream positions preserve appearance without replaying sibling geometry."""
import random


def positioned(seed, words):
    """@cc [owner:fontanierh,label:correctness] explicit-constructor-random-position
    An authored stream position MUST be an explicit bounded seed and count of consumed
    32-bit MT words, independently measured against the prior constructor order. A caller
    MUST verify complete state equality before adopting a measured position. Cached Gaussian
    state is not represented here and MUST refuse that proof rather than disappear. No
    sibling constructor or exported mesh may be executed to recover a production position.
    """
    if type(seed) is not int or type(words) is not int or not 0 <= words <= 10_000_000:
        raise ValueError('Constructor random position requires an explicit bounded integer word count')
    rng = random.Random(seed)
    for _ in range(words):
        rng.getrandbits(32)
    return rng


class Counted:
    """Fixture-only instrumentation of one explicit Random instance, never the global random module."""
    def __init__(self, rng):
        if type(rng) is not random.Random:
            raise ValueError('Explicit Random instance required')
        self.rng = rng
        self.words = 0
        self._random, self._bits = rng.random, rng.getrandbits

    def __enter__(self):
        def draw():
            value = self._random()
            self.words += 2
            return value
        def bits(width):
            value = self._bits(width)
            self.words += (width + 31) // 32
            return value
        self.rng.random, self.rng.getrandbits = draw, bits
        return self

    def context(self, seed):
        if positioned(seed, self.words).getstate() != self.rng.getstate():
            raise ValueError('Measured constructor stream has unrepresented state or a different seed')
        return dict(seed=seed, prefix_words=self.words)

    def __exit__(self, *_):
        self.rng.random, self.rng.getrandbits = self._random, self._bits
