"""Deterministic experimental ledger assembly; unresolved facts block acceptance."""
import re
from collections import defaultdict
from pydantic import ValidationError
from .fact_ledger import reduce_ledger, validate_batch
from .generate_module import merge_parts, project_grading
from .partials import GRADING_EXTRACTION
from ..utils.documents import DocumentError


def assemble_ledger(ledger, blocks):
    originals = {b['id']: b for b in blocks}
    covered = [identifier for batch in ledger for identifier in batch.covered]
    if len(covered) != len(set(covered)) or set(covered) != set(originals):
        raise DocumentError('Ledger coverage could not be verified.', 422, 'ledger_unverified')
    for batch in ledger:
        validate_batch(batch, [originals[identifier] for identifier in batch.covered])
    facts = reduce_ledger(ledger)
    records = defaultdict(dict)
    citations, issues, notes = {}, [], []
    for fact in facts:
        identity = (fact['kind'], fact['key'], fact['field'])
        if len(fact['candidates']) != 1:
            issues.append({'code': 'differing_source_values', 'kind': fact['kind'],
                           'key': fact['key'], 'field': fact['field'], 'candidates': fact['candidates']})
            continue  # Neither source wins, including for optional fields.
        candidate = fact['candidates'][0]
        records[(fact['kind'], fact['key'])][fact['field']] = candidate['value']
        citations[identity] = candidate['evidence']
    module = records[('module', 'module')]
    code = module.get('code', '')
    slug = ''.join(c for c in code.lower() if c.isascii() and c.isalnum())
    literal = r'(?<![A-Za-z0-9])' + r'[\s_-]*'.join(re.escape(c) for c in slug) + r'(?![A-Za-z0-9])'
    if not slug or not any(re.search(literal, b['content'], re.I) for b in blocks):
        issues.append({'code': 'unverified_module_code', 'field': 'code'})
    if not module.get('name'):
        issues.append({'code': 'missing_module_name', 'field': 'name'})
    if 'hasExam' not in module:
        issues.append({'code': 'unknown_exam_structure', 'field': 'hasExam'})
    def identifier(key):
        return key if key.startswith(slug + '-') else slug + '-' + key
    assessments, formula, papers, groups, recesses, opportunities = [], [], [], [], [], []
    for (kind, key), values in list(records.items()):
        if kind == 'assessment':
            values = dict(values)
            for field, default in [('name', ''), ('type', None), ('maxScore', None)]:
                if field not in values:
                    issues.append({'code': 'missing_assessment_field', 'key': key, 'field': field})
                    if default is not None:
                        values[field] = default
            if 'type' in values:
                assessments.append({'id': identifier(key), **values})
        elif kind == 'formula':
            _, reference = key.split(':', 1)
            if 'weight' not in values:
                issues.append({'code': 'missing_formula_weight', 'key': key, 'field': 'weight'})
            formula.append({'componentId': identifier(reference), 'weight': -1, **values})
        elif kind == 'paper':
            papers.append({'id': identifier(key), 'name': '', 'maxScore': -1, 'duration': '', 'studyUnits': '', **values})
        elif kind == 'group':
            groups.append({'id': identifier(key), 'label': '', 'language': '', 'lecturer': '', 'email': '', 'office': '', **values})
        elif kind == 'recess':
            recesses.append({'start': '', 'end': '', **values})
        elif kind == 'opportunity':
            if not values.get('start') or not values.get('end'):
                issues.append({'code': 'incomplete_opportunity_range', 'key': key})
            else:
                opportunities.append({'label': '', **values})
        elif kind == 'note':
            notes.append(values['text'])
    requirements = records.get(('pass', 'module'), {})
    has_exam = module.get('hasExam', False)
    minimum = requirements.get('participationMin' if has_exam else 'finalMin', -1)
    grading = {'assessments': assessments, 'participationFormula': {'components': formula, 'minimumToPass': minimum},
               'hasExam': has_exam, 'passRequirements': requirements or None,
               'finalMarkFormula': records.get(('final', 'module')),
               'examInfo': {'papers': papers, **records.get(('examRule', 'module'), {})} if papers else None,
               'dataNote': '\n\n'.join(notes) or None}
    identity = {k: v for k, v in module.items() if k in ('code', 'name', 'lecturer', 'email', 'office', 'consultationHours')}
    identity = {'code': '', 'name': '', **identity}
    if groups:
        identity['groups'] = groups
    calendar = {'semesterStart': '', 'semesterEnd': '', **{k: v for k, v in module.items()
        if k in ('semesterStart', 'semesterEnd', 'examDate', 'examDateEnd')},
        'recessPeriods': recesses or None, 'examOpportunities': opportunities or None}
    for field, target in [('semesterEnd', 'semesterEndSource'), ('examDate', 'examDateSource')]:
        refs = citations.get(('module', 'module', field), [])
        if refs:
            calendar[target] = {'blockId': refs[0]['block'], 'quote': refs[0]['quote']}
    proposal = {'identity': identity, 'grading': grading, 'calendar': calendar}
    result = None
    # Even a valid Module cannot silently close unresolved ledger contradictions.
    # All proposal/candidate details remain available for owner review.
    try:
        projected = project_grading(GRADING_EXTRACTION.model_validate(grading), {'moduleId': slug})
        assembled = merge_parts({'identity': identity, 'grading': projected, 'calendar': calendar},
                                notes, blocks, blocks)
        if not issues:
            result = assembled
    except ValidationError as error:
        issues.extend({'code': 'incomplete_structure', 'field': '.'.join(map(str, item['loc']))}
                      for item in error.errors())
    except DocumentError as error:
        issues.append({'code': error.code})
        issues.extend(getattr(error, 'issues', []))
    return {'status': 'draft_requires_source_review' if result else 'needs_review',
            'result': result.model_dump(exclude_none=True) if result else None,
            'proposal': proposal, 'issues': issues, 'facts': facts,
            'academicDatabaseWritten': False}
