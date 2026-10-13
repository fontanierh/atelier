"""Match Unreal's bool-plus-output binding without accepting a failed native validation."""
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

validate = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'unreal/Scripts/skin_morph_contacts.py'))['validate_contact_data']


@pytest.mark.parametrize('receipt', ['mesh valid; 16 targets', ''])
def test_success_receipt_is_returned_without_tuple_unpacking(receipt):
    mesh, required, calls = object(), ['Native_NoxSeat_L70_R0'], []

    def native(asset, names):
        calls.append((asset, names))
        return receipt

    library = SimpleNamespace(validate_skin_morph_contacts=native)
    assert validate(library, mesh, required) == receipt
    assert calls == [(mesh, required)]


def test_native_false_becomes_none_and_fails_validation():
    library = SimpleNamespace(validate_skin_morph_contacts=lambda asset, names: None)
    with pytest.raises(RuntimeError, match='validation failed'):
        validate(library, object(), ['missing target'])


@pytest.mark.parametrize('unexpected', [True, False, (True, 'valid'), (False, 'invalid')])
def test_unexpected_binding_shape_cannot_pass(unexpected):
    library = SimpleNamespace(validate_skin_morph_contacts=lambda asset, names: unexpected)
    with pytest.raises(TypeError, match='Unexpected native'):
        validate(library, object(), [])
