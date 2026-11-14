"""Offline budget planning for the experimental ledger; sends no provider requests."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(args):
    from app.ai.fact_ledger import sections, plan_batches, request_cost, indexed_sources, VERSION
    from app.ai.provider import model_for
    from app.utils.document_process import extract_source_isolated
    from app.utils.documents import DocumentError, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_FILES
    files = [file.resolve() for file in args.files]
    if (not 1 <= len(files) <= MAX_FILES or len({file.name.casefold() for file in files}) != len(files)
            or any(not file.is_file() or file.suffix.lower() not in {'.pdf', '.docx'} for file in files)):
        raise DocumentError('Choose up to five distinct PDF/DOCX inputs.', 413, 'invalid_plan_inputs')
    if args.model:
        os.environ['GROQ_FACTS_MODEL'] = args.model
    sources, total = [], 0
    for file in files:
        with file.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        total += len(raw)
        if len(raw) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise DocumentError('Input files exceed the existing upload limit.', 413, 'file_too_large')
        mime = 'application/pdf' if file.suffix.lower() == '.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        source, _ = extract_source_isolated(file.name, raw, mime)
        sources.append(source)
    blocks = sections(sources, max_bytes=2500)
    batches = plan_batches(blocks)
    return {'engine': f'fact-ledger-v{VERSION}-experiment', 'providerCalls': 0, 'model': model_for('facts'),
        'files': len(files), 'sections': len(blocks), 'plannedBatches': len(batches),
        'requestEstimates': [request_cost(batch) for batch in batches],
        'retryEstimates': [request_cost(batch, retry=True) for batch in batches],
        'indexedSourceJsonBytes': len(json.dumps(indexed_sources(blocks), ensure_ascii=False, separators=(',', ':')).encode()),
        'scope': 'Conservative planning estimate including reserved output; not provider usage or fact-accuracy proof'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', nargs='+', type=Path, required=True)
    parser.add_argument('--model', choices=('openai/gpt-oss-20b', 'openai/gpt-oss-120b'))
    args = parser.parse_args()
    try:
        print(json.dumps(main(args), indent=2))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'code': getattr(error, 'code', 'planning_failed'),
                          'exceptionType': type(error).__name__, 'providerCalls': 0}))
        raise SystemExit(1)
