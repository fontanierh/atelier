"""Check both players and both observers, using only native feature receipts."""
import json
import math


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def flying_ship(receipt):
    return (type(receipt.get('ship_stage')) is int and receipt['ship_stage'] in (3, 4, 5) and
            all(type(receipt.get(key)) is int and receipt[key] >= 0 for key in ('dock', 'destination')) and
            receipt['dock'] != receipt['destination'] and finite_number(receipt.get('ship_z')))


def separate_seats(receipt):
    rows = receipt.get('views', [])
    return (len(rows) == 2 and all(finite_number(row.get(key)) for row in rows for key in ('x', 'y', 'z')) and
            sum((rows[0][key] - rows[1][key])**2 for key in ('x', 'y')) > 2500)


def feature_render_checks(folder, case):
    from PIL import Image
    checks = {}
    for phase in range(4 if case == 'zeppelin' else 5):
        try:
            with Image.open(folder / f'feature-{phase}.png') as capture:
                valid = capture.format == 'PNG' and capture.size == (960, 540)
                capture.verify()
            if valid:
                with Image.open(folder / f'feature-{phase}.png') as capture:
                    capture.load()
        except (OSError, ValueError, SyntaxError):
            valid = False
        checks[f'feature_{phase}_rendered_capture'] = valid
    return checks


def feature_checks(folder, case):
    result = json.loads((folder / 'features-result.json').read_text())
    stages = result.get('stages', [])
    last = 3 if case == 'zeppelin' else 4
    checks = {'feature_case_completed': result.get('passed') is True and result.get('case') == case,
              'feature_default_vehicles_enabled': result.get('default_vehicles') is True,
              'feature_all_stages_observed': [s.get('phase') for s in stages] == list(range(last+1))}
    original_ids = None
    epochs = {}
    identities = {}
    original_classes = {}
    mount_retries = {'host': 0, 'guest': 0}
    mount_epochs = {'host': [], 'guest': []}
    kind = 1 if case.startswith('switch-skate') else {'switch-bike': 2, 'switch-sail': 3, 'zeppelin': 4}.get(case, 0)
    for s in stages:
        phase = s['phase']
        for side in ('host', 'guest'):
            rows = s.get(side, {}).get('views', [])
            prefix = f'feature_{phase}_{side}_'
            ids = {r.get('player') for r in rows}
            if original_ids is None:
                original_ids = ids
                original_classes = {r['player']: r.get('pawn') for r in rows}
            checks[prefix+'players'] = (len(rows) == len(ids) == 2 and ids == original_ids and
                                        all(isinstance(i, str) and i for i in ids) and sum(r.get('local') is True for r in rows) == 1)
            checks[prefix+'health'] = all(r.get('health') == 73 and r.get('hits') == 2 for r in rows)
            checks[prefix+'equipment_attachment'] = all(r.get('ready') is True and r.get('attachment') is True for r in rows)
            checks[prefix+'pawn_class'] = all(isinstance(r.get('pawn'), str) and bool(r['pawn']) for r in rows)
            if case == 'equipment':
                checks[prefix+'prediction_roles'] = all(r.get('local_role') in (1, 2, 3) and
                                                        r.get('predicts_moves') is (r.get('local_role') in (2, 3)) for r in rows)
                armed = phase in (1, 2, 3)
                checks[prefix+'armed'] = all(r.get('armed') is armed for r in rows)
                if phase == 2:
                    checks[prefix+'guard'] = all(r.get('guard') is True and r.get('guard_weight', 0) > .8 for r in rows)
                if phase == 3:
                    checks[prefix+'owner_checkpoints'] = any(r.get('local') is True and r.get('checkpoints', 0) >= 3 for r in rows) if side == 'guest' else True
            else:
                if kind:
                    retries = s.get(side, {}).get('mount_recovery_retries')
                    recovery_epochs = s.get(side, {}).get('mount_recovery_epochs')
                    checks[prefix+'mount_recovery_receipt'] = (type(retries) is int and retries >= mount_retries[side] and
                                                              isinstance(recovery_epochs, list) and len(recovery_epochs) == retries and
                                                              recovery_epochs[:len(mount_epochs[side])] == mount_epochs[side] and
                                                              all(isinstance(e, dict) and
                                                                  all(type(e.get(k)) is int and e[k] > 0 for k in ('old_epoch', 'new_epoch')) and
                                                                  e['old_epoch'] != e['new_epoch'] for e in recovery_epochs))
                    if type(retries) is int:
                        mount_retries[side] = retries
                    if isinstance(recovery_epochs, list):
                        mount_epochs[side] = recovery_epochs
                if case == 'switch-bike' and phase == 4:
                    speed = s[side].get('bike_exit_speed')
                    checks[prefix+'stopped_dismount_input'] = (s[side].get('bike_exit_sent') is True and
                                                              s[side].get('bike_exit_grounded') is True and
                                                              type(speed) in (int, float) and abs(speed) <= 40)
                if case == 'switch-sail' and phase == 4:
                    distance = s[side].get('sail_shore_distance')
                    requests = s[side].get('sail_exit_requests')
                    checks[prefix+'returned_to_shore'] = (s[side].get('sail_landing_grounded') is True and
                                                         type(requests) is int and requests >= 1 and
                                                         type(distance) in (int, float) and 0 <= distance <= 1500)
                activity = kind if phase not in (0, last) else 0
                checks[prefix+'activity'] = all(r.get('activity') == activity for r in rows)
                expected = 'Modori' if (phase >= 2 and case == 'zeppelin') or phase == 2 else 'Cairo'
                checks[prefix+'rider'] = all(r.get('rider') == expected for r in rows)
                if case.startswith('switch-skate') and phase in (1, 2, 3):
                    remote = next((r for r in rows if r.get('local') is False), {})
                    observed, matching = (remote.get(k) for k in ('observed_pose_frames', 'matching_pose_frames'))
                    checks[prefix+'displayed_replacement_pose'] = (type(observed) is int and type(matching) is int and
                                                                  observed >= 30 and observed * .95 <= matching <= observed)
                    mesh_matches, error = (remote.get(k) for k in ('matching_mesh_frames', 'mesh_world_error'))
                    checks[prefix+'displayed_body_world_frame'] = (type(observed) is int and type(mesh_matches) is int and
                                                                  observed >= 30 and observed * .95 <= mesh_matches <= observed and
                                                                  type(error) in (int, float) and 0 <= error <= 1 and
                                                                  remote.get('body_visible') is True)
                if phase == 2:
                    checks[prefix+'replacement_class'] = all(r.get('pawn') != original_classes.get(r.get('player')) for r in rows)
                    if case.startswith('switch-skate'):
                        owner = next((r for r in rows if r.get('local') is True), {})
                        checks[prefix+'continued_simulation'] = owner.get('continued_at_tick', 0) > 30 and owner.get('simulation_tick', 0) >= owner.get('continued_at_tick', 0)
                        if case == 'switch-skate-air':
                            checks[prefix+'air_continuation'] = s[side].get('requested_in_air') is True and owner.get('continued_mode') == 2
                        if case == 'switch-skate-bail':
                            checks[prefix+'bail_recovered_before_swap'] = s[side].get('requested_in_bail') is True and owner.get('continued_mode') == 1
                if phase in (3, 4) and case != 'zeppelin':
                    checks[prefix+'returned_class'] = all(r.get('pawn') == original_classes.get(r.get('player')) for r in rows)
                if case.startswith('switch-skate') and phase in (2, 3):
                    owner = next((r for r in rows if r.get('local') is True), {})
                    lift, root, z, half = (owner.get(k) for k in ('body_lift', 'ride_root_z', 'z', 'standing_half'))
                    checks[prefix+'replacement_height'] = (all(isinstance(v, (int, float)) for v in (lift, root, z, half)) and
                                                            abs(lift-half) < 1 and abs(z-root-lift) < 1)
                for r in rows:
                    key = (side, r.get('player'))
                    old = epochs.get(key, 0)
                    epoch = r.get('epoch')
                    identity = tuple(r.get(field) for field in ('activity', 'rider', 'pawn'))
                    changed = key in identities and identities[key] != identity
                    checks[prefix+'epoch_'+str(r.get('player'))] = type(epoch) is int and epoch >= old and (not changed or epoch > old)
                    epochs[key] = epoch if type(epoch) is int else old
                    identities[key] = identity
        if case == 'zeppelin' and phase in (1, 2):
            a, b = s['host'], s['guest']
            checks[f'feature_{phase}_shared_ship'] = (flying_ship(a) and flying_ship(b) and
                                                      a['dock'] == b['dock'] and a['destination'] == b['destination'] and
                                                      abs(a['ship_z']-b['ship_z']) < 250)
            checks[f'feature_{phase}_separate_seats'] = separate_seats(a) and separate_seats(b)
    return checks
