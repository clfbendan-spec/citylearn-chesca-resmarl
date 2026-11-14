"""Evidence-calibrated headroom; an observed best is not a certified optimum."""
import math

from evaluation_contract import physical_protocol_id


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('invalid_metric')
    return value


def _metrics(result):
    rows = result['per_building']
    if not rows or set(rows) != set(result['protocol']['building_ids']):
        raise ValueError('incomparable_buildings')
    for row in rows.values():
        if _number(row['positive_bill']) < 0:
            raise ValueError('negative_positive_bill')
        if not 0 <= _number(row['discomfort_proportion']) <= 1:
            raise ValueError('invalid_discomfort')
        if type(row.get('occupied_samples')) is not int or row['occupied_samples'] <= 0:
            raise ValueError('missing_occupied_samples')
    return math.fsum(row['positive_bill'] for row in rows.values()), all(
        row['discomfort_proportion'] < .10 for row in rows.values())


def compute_headroom(result, baseline=None, best=None, bound=None):
    report = dict(status='unavailable', reference_type='independent_nocontrol',
                  reference_id=None, scope='whole_building',
                  verified_saving=None, verified_saving_fraction=None,
                  observed_candidate_delta=None, optimistic_bound=None,
                  bound_certificate=None, service_deltas={}, terminal_deltas={},
                  unknown_reasons=['whole_building_remaining_unknown'])
    try:
        bill, qualified = _metrics(result)
        report['current_comfort_qualified'] = qualified
        if baseline is None:
            raise ValueError('missing_independent_nocontrol')
        if baseline.get('algorithm') != 'NoControl':
            raise ValueError('reference_is_not_nocontrol')
        if (not result.get('protocol') or not baseline.get('protocol')
                or physical_protocol_id(result['protocol'])
                != physical_protocol_id(baseline['protocol'])):
            raise ValueError('incomparable_baseline_protocol')
        if result['protocol'].get('information_access') != baseline['protocol'].get('information_access'):
            report['unknown_reasons'].append('different_information_access_reference')
            report['comparison_scope'] = 'physical_protocol_only'
        else:
            report['comparison_scope'] = 'full_protocol'
        base_bill, base_qualified = _metrics(baseline)
        report.update(status='available', reference_id=baseline.get('task_id'),
                      baseline_comfort_qualified=base_qualified,
                      verified_saving=_number(base_bill - bill),
                      verified_saving_fraction=_number((base_bill - bill) / base_bill) if base_bill > 0 else None)
        if not qualified:
            report['unknown_reasons'].append('current_comfort_failed')
        if not base_qualified:
            report['unknown_reasons'].append('baseline_comfort_failed')
        for name, row in result['per_building'].items():
            for field, target in (('terminal_state', 'terminal_deltas'),
                                  ('service_diagnostics', 'service_deltas')):
                prior = baseline['per_building'][name].get(field, {})
                current = row.get(field, {})
                deltas = {}
                for key in current.keys() & prior.keys():
                    try:
                        deltas[key] = _number(_number(current[key]) - _number(prior[key]))
                    except ValueError:
                        pass
                report[target][name] = deltas
        if best is not None:
            if best.get('protocol') != result['protocol']:
                report['unknown_reasons'].append('incomparable_observed_candidate')
            else:
                best_bill, best_qualified = _metrics(best)
                if best_qualified and qualified:
                    report['observed_candidate_delta'] = _number(bill - best_bill)
                    report['observed_candidate_id'] = best.get('task_id')
                else:
                    report['unknown_reasons'].append('observed_comparison_comfort_failed')
        if bound is not None:
            # A certificate verifier is intentionally not implemented here.
            # Even a payload saying "verified" cannot certify its own bound.
            report['unknown_reasons'].append('conditional_bound_not_whole_building'
                                            if bound.get('scope') != 'whole_building'
                                            else 'bound_certificate_not_independently_verified')
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as error:
        report.update(status='unavailable', verified_saving=None, verified_saving_fraction=None)
        report['unknown_reasons'].append(str(error) if isinstance(error, ValueError) else 'malformed_evidence')
    return report
