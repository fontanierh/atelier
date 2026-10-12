"""Check both players and both observers, using only native feature receipts."""
import json


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
    original_classes = {}
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
                activity = kind if phase not in (0, last) else 0
                checks[prefix+'activity'] = all(r.get('activity') == activity for r in rows)
                expected = 'Modori' if (phase >= 2 and case == 'zeppelin') or phase == 2 else 'Cairo'
                checks[prefix+'rider'] = all(r.get('rider') == expected for r in rows)
                if case.startswith('switch-skate') and phase in (1, 2, 3):
                    remote = next((r for r in rows if r.get('local') is False), {})
                    observed, matching = (remote.get(k) for k in ('observed_pose_frames', 'matching_pose_frames'))
                    checks[prefix+'displayed_replacement_pose'] = (type(observed) is int and type(matching) is int and
                                                                  observed >= 30 and observed * .95 <= matching <= observed)
                if phase == 2:
                    checks[prefix+'replacement_class'] = all(r.get('pawn') != original_classes.get(r.get('player')) for r in rows)
                    if case.startswith('switch-skate'):
                        owner = next((r for r in rows if r.get('local') is True), {})
                        checks[prefix+'continued_simulation'] = owner.get('continued_at_tick', 0) > 30 and owner.get('simulation_tick', 0) >= owner.get('continued_at_tick', 0)
                        if case == 'switch-skate-air':
                            checks[prefix+'air_continuation'] = s[side].get('requested_in_air') is True and owner.get('continued_mode') == 2
                        if case == 'switch-skate-bail':
                            checks[prefix+'bail_recovered_before_swap'] = s[side].get('requested_in_bail') is True and owner.get('continued_mode') == 1
                if case.startswith('switch-skate') and phase in (2, 3):
                    owner = next((r for r in rows if r.get('local') is True), {})
                    lift, root, z, half = (owner.get(k) for k in ('body_lift', 'ride_root_z', 'z', 'standing_half'))
                    checks[prefix+'replacement_height'] = (all(isinstance(v, (int, float)) for v in (lift, root, z, half)) and
                                                            abs(lift-half) < 1 and abs(z-root-lift) < 1)
                for r in rows:
                    key = (side, r.get('player'))
                    old = epochs.get(key, 0)
                    epoch = r.get('epoch')
                    checks[prefix+'epoch_'+str(r.get('player'))] = type(epoch) is int and epoch >= old and (phase != 2 or epoch > old)
                    epochs[key] = epoch if type(epoch) is int else old
        if case == 'zeppelin' and phase in (1, 2):
            a, b = s['host'], s['guest']
            checks[f'feature_{phase}_shared_ship'] = (a.get('dock') == b.get('dock') and a.get('destination') == b.get('destination') and
                                                      abs(a.get('ship_z', 0)-b.get('ship_z', 0)) < 250)
            rows = a.get('views', [])
            checks[f'feature_{phase}_separate_seats'] = len(rows) == 2 and sum((rows[0].get(k, 0)-rows[1].get(k, 0))**2 for k in ('x', 'y')) > 2500
    return checks
