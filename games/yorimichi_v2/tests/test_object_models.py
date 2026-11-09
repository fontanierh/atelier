import importlib.util
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
spec = importlib.util.spec_from_file_location('object_models', GAME / 'tools/migrate/object_models.py')
object_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(object_models)


def test_every_region_object_names_existing_models():
    """A recovery that splits or deletes a shared record must move the region object lists with its consumers."""
    found = object_models.dangling(GAME)
    assert not found, {rid: sorted(items)[:3] for rid, items in found.items()}


def test_one_model_is_a_string_and_several_a_list():
    assert object_models._value(['prop/a']) == '"prop/a"'
    assert object_models._value(['prop/a', 'prop/b']) == '["prop/a", "prop/b"]'
