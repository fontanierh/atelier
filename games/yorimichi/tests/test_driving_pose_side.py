from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT.parents[1] / "platform/engine/Plugins/Activities/Driving/Source/AtelierDriving"


def test_runtime_grip_frame_uses_the_same_left_right_signs():
    header = (PLUGIN / "Public/DrivingComponent.h").read_text()
    source = (PLUGIN / "Private/DrivingComponent.cpp").read_text()

    # Unreal rider component space is +X forward, +Y right; the rider's left is -Y.
    assert "constexpr float Sign(int Side) { return Side ? 1.f : -1.f; }" in header
    assert 'static_assert(Sign(0) == -1.f' in header
    assert 'static_assert(Sign(1) == 1.f' in header

    for function in ("HandPoint", "GripUp", "GripAxis"):
        start = source.index(f"FVector UDrivingComponent::{function}")
        end = source.index("\n}", start)
        assert "AtelierDrivingSide::Sign(Side)" in source[start:end]

    # The committed 474ee2e5 version had the mirrored literal in all three functions.
    assert "const float Sign = Side ? -1.f : 1.f;" not in source
