"""Entry adapter for community assessments executed by the normal task manager."""
import argparse
import base64
import json
import sys
from pathlib import Path


def run_if_requested(algorithm):
    if '--community-assessment-schema' not in sys.argv:
        return
    parser = argparse.ArgumentParser()
    parser.add_argument('--community-assessment-schema', required=True)
    parser.add_argument('--community-assessment-output', required=True)
    parser.add_argument('--community-assessment-parameters', required=True)
    parser.add_argument('--output-dir', required=True)
    args, _ = parser.parse_known_args()
    parameters = json.loads(base64.b64decode(args.community_assessment_parameters, validate=True))
    output = Path(args.output_dir)
    (output / 'chesca_agent_config.json').write_text(
        json.dumps(parameters, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    from community_assessment import run_assessment
    result = run_assessment(args.community_assessment_schema, args.community_assessment_output,
                            algorithm=algorithm, parameters=parameters, task_output=args.output_dir)
    case = result['baseline'] if algorithm == 'NOCONTROL' else next(
        (case for case in result.get('cases', []) if case['id'] == 'chesca'), None)
    if result['status'] != 'succeeded' or not case or case['status'] != 'succeeded':
        raise RuntimeError(result.get('error') or (case or {}).get('error') or 'Community assessment failed')
    import pandas as pd
    table = pd.DataFrame(case['metrics']['officialRows']).pivot(index='cost_function', columns='name', values='value')
    table.to_csv(output / 'exported_kpis.csv')
    from utils.report import print_kpis_for_java
    print_kpis_for_java(table)
    (output / 'community_assessment_result.json').write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    sys.exit(0)
