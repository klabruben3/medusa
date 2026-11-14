"""Reject source-role mistakes independently of model schema compliance."""
import json
import re
from datetime import date
from .table_context import mentioned_dates, source_year, event_keys

DATE_FIELDS = {'date', 'dateEnd', 'dateAvailable', 'semesterStart', 'semesterEnd', 'examDate', 'examDateEnd', 'start', 'end'}
START = re.compile(r'\b(?:semester\s+(?:starts?|begins?|commences?)|start\s+of\s+(?:the\s+)?semester|semesterbegin)\b', re.I)
END = re.compile(r'\b(?:semester\s+(?:ends?|concludes?|eindig)|end\s+of\s+(?:the\s+)?semester|semestereinde)\b', re.I)


def key_alias(key):
    match = re.search(r'(?:^|-)(?:(?:class|weekly)-)?test-?(\d+)$', key)
    return 'test-' + str(int(match.group(1))) if match else key


def evidence_text(cite):
    try:
        row = json.loads(cite.quote)
        if isinstance(row, list):
            return ' '.join(str(value) for value in row)
    except (ValueError, TypeError):
        pass
    return cite.quote


def contexts(observation, originals):
    found = []
    for cite in observation.evidence:
        block = originals[cite.block]
        rows = block.get('row_context', [])
        if cite.row is not None and 0 <= cite.row < len(rows) and rows[cite.row]:
            found.append(rows[cite.row])
    return found


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def supported_date(observation, value, originals):
    if not valid_date(value):
        return False
    table_rows = contexts(observation, originals) if observation.kind == 'assessment' else []
    if table_rows:
        matching = [row for row in table_rows if any(key_alias(key) == key_alias(observation.key) for key in row['event_keys'])]
        return any(row['date'] == value and row['date_state'] in {'explicit', 'inherited'} for row in matching)
    return any(value in mentioned_dates(evidence_text(cite), source_year(originals[cite.block]['source_file']))
               for cite in observation.evidence)


def boundary_supported(observation, field, value, originals):
    label = START if field == 'semesterStart' else END
    for cite in observation.evidence:
        text = evidence_text(cite)
        for match in label.finditer(text):
            if re.search(r'\b(?:not|never|nie)\b', text[max(0, match.start() - 20):match.start()], re.I):
                continue
            tail = re.split(r'[;\n]|\.(?=\s|$)', text[match.end():match.end() + 100], maxsplit=1)[0]
            # Do not borrow another boundary's date later in the same sentence.
            tail = re.split(r'\b(?:and\s+)?(?:semester\s+(?:starts?|ends?)|(?:start|end)\s+of\s+(?:the\s+)?semester)\b', tail, maxsplit=1, flags=re.I)[0]
            # A relative/negated statement does not provide an actual boundary.
            if re.match(r'\s*(?:[:–—-]\s*)?(?:(?:on|op|is)\s+)?(?:not|before|after|nie|voor|na)\b', tail, re.I):
                continue
            if value in mentioned_dates(tail, source_year(originals[cite.block]['source_file'])):
                return True
    return False


def verify_source_role(observation, field, value, originals):
    text = ' '.join(evidence_text(cite) for cite in observation.evidence)
    table_rows = contexts(observation, originals) if observation.kind == 'assessment' else []
    if table_rows and not any(key_alias(observation.key) in {key_alias(key) for key in row['event_keys']} for row in table_rows):
        raise ValueError('assessment identity does not match its cited row')
    if observation.kind == 'assessment' and not table_rows:
        keys = event_keys(text)
        if keys and key_alias(observation.key) not in {key_alias(key) for key in keys}:
            raise ValueError('assessment identity does not match its cited text')
    if observation.kind == 'module' and field == 'hasExam':
        negative = bool(re.search(r'\b(?:no\s+(?:final\s+)?exam(?:ination)?|geen\s+(?:finale\s+)?eksamen)(?=\s*(?:[.;,:!?]|$))', text, re.I))
        positive_text = re.sub(r'\b(?:exam(?:ination)?|eksamen)\s+(?:period|starts?|begins?|begin)\b|\bno\s+exam(?:ination)?\s+(?:date|information|timetable)\b', '', text, flags=re.I)
        positive = bool(re.search(r'\b(?:exam(?:ination)?|eksamen)\b', positive_text, re.I))
        if not (negative if value is False else positive and not negative):
            raise ValueError('exam structure is not explicitly supported')
    if observation.kind == 'module' and field in {'semesterStart', 'semesterEnd'}:
        if not valid_date(value) or not boundary_supported(observation, field, value, originals):
            raise ValueError('semester boundary is not explicitly supported')
    elif field in DATE_FIELDS and value and not supported_date(observation, value, originals):
        raise ValueError('date is not supported by its source row')
    if observation.kind == 'module' and field in {'examDate', 'examDateEnd'}:
        if (not re.search(r'\b(?:exam(?:ination)?|eksamen)\b', text, re.I)
                or re.search(r'\b(?:exam(?:ination)?|eksamen)\s+(?:period|starts?|begins?|begin)\b', text, re.I)):
            raise ValueError('general exam period is not a module exam slot')
    if observation.kind == 'assessment' and field == 'time':
        if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ValueError('time must be one supported HH:mm instant')
        rows = contexts(observation, originals)
        if rows:
            matching = [row for row in rows if any(key_alias(key) == key_alias(observation.key) for key in row['event_keys'])]
            if not any(row['period_start'] == value and not row['session_only'] for row in matching):
                raise ValueError('a tutorial window is not an exact test start')
        elif value not in text:
            raise ValueError('time is absent from source')
    if observation.kind == 'assessment' and field == 'slots':
        for slot in value:
            if not supported_date(observation, slot['date'], originals):
                raise ValueError('slot date is not supported')
            if slot.get('time'):
                rows = contexts(observation, originals)
                matching = [row for row in rows if any(key_alias(key) == key_alias(observation.key) for key in row['event_keys'])]
                if rows and not any(row['period_start'] == slot['time'] and
                        (not row['session_only'] or re.search(r'session|tutorial|tutoriaal', slot.get('label') or '', re.I)) for row in matching):
                    raise ValueError('slot does not preserve session meaning')
                if not rows and slot['time'] not in text:
                    raise ValueError('slot time is absent from source')
