"""Resolve project/kit CI mode and a pinned evidence-run reference."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_pipeline.ci import resolve_context
from web_pipeline.common import PipelineError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--evidence-run-id', default='')
    parser.add_argument('--force-project', action='store_true')
    args = parser.parse_args()
    try:
        context = resolve_context(Path(args.root), args.base_ref, args.evidence_run_id, args.force_project)
        if os.environ.get('GITHUB_OUTPUT'):
            with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
                for key, value in context.items():
                    # Paths must not create extra workflow output records.
                    text = str(value).lower() if isinstance(value, bool) else str(value)
                    if '\n' in text or '\r' in text:
                        raise PipelineError('Invalid multiline CI output')
                    stream.write(f'{key}={text}\n')
        print(json.dumps(context))
        return 0
    except (PipelineError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
