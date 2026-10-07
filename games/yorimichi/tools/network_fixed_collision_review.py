"""Receipt checks for fixed gameplay collision; no claims about exhaustive triangles."""
import hashlib
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def compare_fixed_collision(server, client):
    checks = {}
    left, right = (r.get('fixed_gameplay_collision', {}) for r in (server, client))
    required = {'JapanWorld', 'SkatePark', 'MegaRamp', 'SuperUltraMegaPark', 'Hippodrome'}
    for role, receipt in (('host', left), ('guest', right)):
        entries = receipt.get('components', [])
        valid_entries = (isinstance(entries, list) and len(entries) >= 5 and
                        all(isinstance(entry, str) and entry for entry in entries))
        checks[role + '_fixed_inventory'] = (valid_entries and entries == sorted(set(entries)) and
            required <= {entry.split(':', 1)[0] for entry in entries} and
            hashlib.sha1('\n'.join(entries).encode()).hexdigest() == receipt.get('inventory_digest'))
        checks[role + '_fixed_responses'] = receipt.get('response_errors') == []
        checks[role + '_stationary_classified'] = receipt.get('excluded_stationary') == []
        probes = receipt.get('probes', [])
        checks[role + '_fixed_probe_coverage'] = (isinstance(probes, list) and len(probes) >= 40 and
            all(isinstance(p, dict) for p in probes) and
            len({(p.get('key'), p.get('complex')) for p in probes}) == len(probes) and
            sum(p.get('visibility_hit') is True for p in probes) == receipt.get('visibility_hits', -1) and
            receipt.get('visibility_hits', 0) >= 10)
        checks[role + '_fixed_probe_matches'] = bool(probes) and all(
            isinstance(p.get('key'), str) and bool(p['key']) and type(p.get('complex')) is bool and
            type(p.get('visibility_hit')) is bool and p.get('visibility_hit') == p.get('fixed_hit') and
            p.get('matches') is True and p.get('unclassified_visibility_hit') is False and
            finite(p.get('z')) and finite(p.get('normal_z')) for p in probes)
    a, b = left.get('probes', []), right.get('probes', [])
    checks['fixed_inventory_matches'] = bool(left.get('components')) and left.get('components') == right.get('components')
    checks['fixed_probe_peer_parity'] = bool(a) and len(a) == len(b) and all(
        all(x.get(k) == y.get(k) for k in ('key', 'complex', 'visibility_hit', 'fixed_hit', 'owner_class', 'mesh_asset', 'instanced', 'item')) and
        (x.get('instanced') is True or x.get('component') == y.get('component')) and
        all(finite(x.get(k)) and finite(y.get(k)) and abs(x[k] - y[k]) <= limit
            for k, limit in (('z', .1), ('normal_z', .001))) for x, y in zip(a, b))
    return checks
