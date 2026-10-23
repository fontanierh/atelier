"""Actual mixed random methods reproduce constructor boundaries without generating siblings."""
import importlib.util
from pathlib import Path
import random

import pytest

p = Path(__file__).resolve().parents[1] / 'world/random_stream.py'
spec = importlib.util.spec_from_file_location('constructor_random_stream', p)
stream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream)


@pytest.mark.parametrize('seed', [76, 49157])
def test_mixed_original_draws_replay_complete_state_at_multiple_constructor_boundaries(seed):
    original = random.Random(seed)
    with stream.Counted(original) as measured:
        for boundary in range(5):
            for _ in range(57 + boundary):
                original.uniform(-2, 3)
                original.randint(0, 44)
                original.randrange(17)
                original.choice(['one', 'two', 'three'])
                original.getrandbits(73)
                original.getrandbits(0)
            assert measured.context(seed) == dict(seed=seed, prefix_words=measured.words)
            restored = stream.positioned(seed, measured.words)
            assert restored.getstate() == original.getstate()
            state = original.getstate()
            assert [restored.random() for _ in range(10)] == [original.random() for _ in range(10)]
            original.setstate(state)
            # The comparison draws are not part of the original construction prefix.
            measured.words -= 20


@pytest.mark.parametrize('words', [-1, True, 1.5, 10_000_001])
def test_unbounded_or_ambiguous_random_positions_refuse(words):
    with pytest.raises(ValueError):
        stream.positioned(76, words)


def test_cached_gaussian_context_cannot_be_adopted_as_a_plain_word_position():
    rng = random.Random(76)
    with stream.Counted(rng) as measured:
        rng.gauss(0, 1)
        with pytest.raises(ValueError, match='unrepresented state'):
            measured.context(76)
