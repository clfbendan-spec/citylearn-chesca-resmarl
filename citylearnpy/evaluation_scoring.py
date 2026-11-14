"""Shared, read-only scoring contract for the 2026-11-11 research protocol."""
import math


FORMULA_VERSION = 'native-piecewise-20261111'
PROTOCOL_FIELDS = (
    'dataset_files_sha256', 'simulation_window', 'seconds_per_time_step',
    'building_ids', 'equipment_sha256', 'initial_state_sha256',
    'evaluator_version', 'cost_definition', 'information_access', 'warmup',
    'action_contract', 'environment_step_order',
    'outage_model_sha256',
)


def penalty(d):
    """d is percentage points: 5 means 5%, not 0.05."""
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or not 0 <= d <= 100:
        raise ValueError('invalid_discomfort_percentage')
    return min(d, 3) + 3 * min(max(d - 3, 0), 2) + 5 * min(max(d - 5, 0), 3) + 10 * max(d - 8, 0)


def _finite(value, lower=0, strictly=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (value <= lower if strictly else value < lower)):
        raise ValueError('invalid_numeric_metric')
    return value


def _unavailable(reason):
    return dict(status='unavailable', score=None, rankable=False,
                comfort_qualified=None, reason_codes=[reason],
                per_building={}, formula_version=FORMULA_VERSION)


def _derived(value):
    if not math.isfinite(value):
        raise ValueError('nonfinite_derived_score')
    return value


def _validate_protocol(result, anchor):
    current, reference = result.get('protocol', {}), anchor.get('protocol', {})
    for field in PROTOCOL_FIELDS:
        for protocol in (current, reference):
            if field not in protocol or protocol[field] is None or protocol[field] == '':
                raise ValueError('missing_protocol:' + field)
        if current[field] != reference[field]:
            raise ValueError('incomparable_protocol:' + field)
    names = current['building_ids']
    if (not isinstance(names, list) or not names or len(set(names)) != len(names)
            or any(not isinstance(name, str) or not name for name in names)):
        raise ValueError('invalid_building_ids')
    if set(result.get('per_building', {})) != set(names) or set(anchor.get('per_building', {})) != set(names):
        raise ValueError('incomparable_buildings')
    window = current['simulation_window']
    if (not isinstance(window, list) or len(window) != 2
            or any(type(v) is not int for v in window) or window[0] < 0 or window[1] <= window[0]):
        raise ValueError('invalid_window')
    _finite(current['seconds_per_time_step'], strictly=True)
    if not anchor.get('anchor_id') or not anchor.get('anchor_checkpoint_sha256'):
        raise ValueError('missing_registered_anchor_identity')
    return names


def compute_score(result: dict, anchor: dict, alpha: float = 1.0) -> dict:
    """Score valid comparable evidence; unknown results never become zero.

    Anchor file/checkpoint hashes must be verified by the artifact loader before
    calling this pure function. Native and cash scores share comfort terms but
    keep their own denominators. Service and terminal inventories are diagnostics.
    """
    if anchor is None:
        return _unavailable('missing_anchor')
    try:
        _finite(alpha)
        names = _validate_protocol(result, anchor)
        per, cash, cash_errors = {}, {}, []
        for name in names:
            row, base = result['per_building'][name], anchor['per_building'][name]
            for item in (row, base):
                count = item.get('occupied_samples')
                if type(count) is not int or count <= 0:
                    raise ValueError('missing_occupied_samples:' + name)
                d = _finite(item.get('discomfort_proportion'))
                penalty(100 * d)
            cost = _finite(row.get('cost_total'))
            anchor_cost = _finite(base.get('cost_total'), strictly=True)
            delta_p = penalty(100 * row['discomfort_proportion']) - penalty(100 * base['discomfort_proportion'])
            cost_term = _derived(100 * (cost / anchor_cost - 1))
            _derived(cost_term + alpha * delta_p)
            per[name] = dict(cost_total=cost, anchor_cost_total=anchor_cost,
                             discomfort_proportion=row['discomfort_proportion'],
                             anchor_discomfort_proportion=base['discomfort_proportion'],
                             occupied_samples=row['occupied_samples'],
                             cost_term=cost_term, penalty_delta=delta_p,
                             comfort_term=alpha * delta_p,
                             score=cost_term + alpha * delta_p,
                             comfort_qualified=row['discomfort_proportion'] < .10,
                             service_diagnostics=row.get('service_diagnostics'),
                             terminal_state=row.get('terminal_state'))
            try:
                bill = _finite(row.get('positive_bill'))
                anchor_bill = _finite(base.get('positive_bill'), strictly=True)
                cash_term = _derived(100 * (bill / anchor_bill - 1))
                _derived(cash_term + alpha * delta_p)
                cash[name] = dict(positive_bill=bill, anchor_positive_bill=anchor_bill,
                                  cost_term=cash_term, comfort_term=alpha * delta_p,
                                  score=cash_term + alpha * delta_p)
            except ValueError:
                cash_errors.append('missing_or_invalid_cash:' + name)
        qualified = all(row['comfort_qualified'] for row in per.values())
        sensitivity = [dict(alpha=a, score=_derived(math.fsum((v['cost_term'] + a * v['penalty_delta']) / len(per)
                                              for v in per.values()))) for a in (.5, 1., 2.)]
        return dict(status='available', score=_derived(math.fsum(v['score'] / len(per) for v in per.values())),
                    alpha=alpha, rankable=qualified, comfort_qualified=qualified,
                    reason_codes=[] if qualified else ['comfort_gate_failed'],
                    per_building=per, sensitivity=sensitivity, formula_version=FORMULA_VERSION,
                    anchor_id=anchor['anchor_id'], policy_id=result.get('policy_id'),
                    anchor_comfort_qualified=all(
                        anchor['per_building'][name]['discomfort_proportion'] < .10 for name in names),
                    anchor_checkpoint_sha256=anchor['anchor_checkpoint_sha256'],
                    anchor_result_sha256=anchor.get('anchor_result_sha256'),
                    anchor_task_id=anchor.get('task_id'),
                    cash_trial=dict(status='unavailable' if cash_errors else 'available',
                                    score=None if cash_errors else _derived(math.fsum(v['score'] / len(per) for v in cash.values())),
                                    reason_codes=cash_errors, per_building=cash))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        return _unavailable(str(error) if isinstance(error, ValueError) else 'malformed_evidence')


def aggregate_online(scenes: dict) -> dict:
    """Aggregate a frozen policy over all three declared Online scenarios."""
    required = ('online1', 'online2', 'online3')
    if any(name not in scenes for name in required):
        return _unavailable('incomplete_online_scenarios')
    rows = [scenes[name] for name in required]
    if any(row.get('status') != 'available' for row in rows):
        return _unavailable('unavailable_scenario_score')
    if not rows[0].get('policy_id') or any(row.get('policy_id') != rows[0]['policy_id'] for row in rows):
        return _unavailable('different_or_unknown_policies')
    if any(set(row.get('per_building', {})) != set(rows[0]['per_building']) for row in rows):
        return _unavailable('incomparable_buildings')
    if any(row.get('alpha') != rows[0].get('alpha') or row.get('formula_version') != FORMULA_VERSION for row in rows):
        return _unavailable('incomparable_scoring_rules')
    qualified = all(row['comfort_qualified'] for row in rows)
    return dict(status='available', score=sum(row['score'] for row in rows) / 3,
                alpha=rows[0]['alpha'], rankable=qualified, comfort_qualified=qualified,
                policy_id=rows[0]['policy_id'], formula_version=FORMULA_VERSION,
                reason_codes=[] if qualified else ['comfort_gate_failed'],
                scenarios={name: scenes[name]['score'] for name in required})
