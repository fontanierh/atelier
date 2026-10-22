"""Kart handling changes stay in kart parameters; shared driving defaults stay off."""
import re
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
SIM = GAME.parent.parent / 'platform/engine/Plugins/Activities/Driving/Source/AtelierDriving/Private/Simulation'
KART = (SIM / 'SimulationKart.h').read_text()
SPEC = (SIM / 'SimulationSpec.h').read_text()
STEER = (SIM / 'SimulationSteering.cpp').read_text()
ASSISTS = (SIM / 'SimulationVehicleAssists.cpp').read_text()
WORLD = (SIM / 'SimulationVehicleWorld.cpp').read_text()
CHARACTER = (GAME / 'unreal/Source/Yorimichi/WandererCharacter.cpp').read_text()
DRIVING = (GAME.parent.parent / 'platform/engine/Plugins/Activities/Driving/Source/AtelierDriving/Private/DrivingComponent.cpp').read_text()


def test_kart_lock_curve_and_grip():
    assert 's.tires.has_lock_curve = true;' in KART
    assert 's.tires.lock_angle_low = 27.0f;' in KART
    assert 's.tires.lock_angle_high = 12.0f;' in KART
    assert 's.tires.lock_speed_low = 3.0f;' in KART
    assert 's.tires.lock_speed_high = 24.6f;' in KART
    assert 's.tires.lock_ramp_time = 0.15f;' in KART
    assert 's.tires.static_grip[1] = 1.35f;' in KART
    assert 's.tires.static_grip[0] = 1.3f;' in KART


def test_kart_suspension_axle_and_ground_alignment():
    assert 's.chassis.travel[0] = 4.5f;' in KART
    assert 's.chassis.travel[1] = 4.5f;' in KART
    assert 's.transmission.solid_axle[1] = true;' in KART
    assert 's.wheel_ground_reference = true;' in KART
    assert 's.body.collision_bottom_raise = 0.04f;' in KART
    assert 's.kart_alignment_assist = true;' in KART
    assert 'if (Spec.kart_alignment_assist)' in DRIVING
    assert 'Car->Chassis.jump_config.alignment.pitch = 1.f;' in DRIVING
    assert 'ground_reference.normal' in WORLD and 'has_ground_reference = true;' in WORLD
    assert 'trans.solid_axle[axle]' in ASSISTS


def test_kart_drift_waits_for_the_handbrake_and_stabilizes_early():
    assert 's.drift_requires_request = true;' in KART
    assert 's.stability_assist = true;' in KART
    assert 's.drift_assist_min_speed = 3.0f;' in KART
    assert 's.drift_assist_min_slip = 0.10471976f;' in KART
    assert 'spec.drift_requires_request' in ASSISTS
    assert 'spec.stability_assist' in ASSISTS


def test_shared_driving_knobs_default_to_todays_behaviour():
    assert 'bool has_lock_curve = false;' in SPEC
    assert 'bool solid_axle[2] = {false, false};' in SPEC
    assert 'float collision_bottom_raise = 0.0f;' in SPEC
    assert 'bool drift_requires_request = false;' in SPEC
    assert 'bool stability_assist = false;' in SPEC
    assert 'bool wheel_ground_reference = false;' in SPEC
    assert 'if (i.has_lock_curve)' in STEER


def test_l1_is_a_tap_and_spawn_tries_all_four_directions():
    kart_hold = re.search(r'CarPad.*?HoldTimeThreshold = ([0-9.]+)f', CHARACTER, re.S)
    assert kart_hold and float(kart_hold.group(1)) <= .15
    assert 'for (const FVector& Direction : {Forward, Right, -Right, -Forward})' in DRIVING
    assert 'for (const float Distance : {200.f, 350.f, 500.f})' in DRIVING


def test_flip_recovery_and_scenarios():
    assert 'Car->SetAutoRight(true);' in CHARACTER
    assert 'InvertedTime >= 1.f' in DRIVING
    assert 'RightingTime / .5f' in DRIVING
    assert '50.f * FMath::Sin(PI * T)' in DRIVING
    assert 'StartRighting(true)' in DRIVING
    for name in ('kart_uneven.py', 'kart_flip.py', 'kart_spawn.py'):
        assert (GAME / 'scenarios' / name).exists(), name
    uneven = (GAME / 'scenarios/kart_uneven.py').read_text()
    assert 'contact_lost_percent' in uneven and 'steer_rms_deg_s' in uneven
