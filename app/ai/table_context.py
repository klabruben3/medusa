"""Source-owned timetable structure, never model-inferred neighbouring values."""
import json
import re
from datetime import date
from .source_calendar import MONTHS

MONTH_INDEX = {name: number for number, names in enumerate(MONTHS, 1) for name in names}
MONTH_INDEX['mrt'] = 3
MONTH_WORDS = '|'.join(sorted(MONTH_INDEX, key=len, reverse=True))
WEEKDAYS = (
    ('mon', 'monday', 'maandag', 'maan'), ('tue', 'tues', 'tuesday', 'dins', 'dinsdag'),
    ('wed', 'wednesday', 'woens', 'woensdag'), ('thu', 'thur', 'thurs', 'thursday', 'dond', 'donderdag'),
    ('fri', 'friday', 'vry', 'vrydag'), ('sat', 'saturday', 'saterdag'), ('sun', 'sunday', 'sondag'))


def source_year(text):
    years = {int(value) for value in re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', text)}
    return next(iter(years)) if len(years) == 1 else None


def parsed_date(text, year=None, numeric_order=None):
    text = ' '.join(str(text).split()).strip()
    match = re.fullmatch(r'((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})', text)
    try:
        if match:
            return date(*map(int, match.groups())).isoformat()
        match = re.fullmatch(r'(\d{1,2})\s*[- /]\s*(' + MONTH_WORDS + r')\.?(?:\s*[- /]\s*((?:19|20)\d{2}))?', text, re.I)
        if match:
            day, month, explicit_year = match.groups()
            use_year = int(explicit_year) if explicit_year else year
            return date(use_year, MONTH_INDEX[month.lower()], int(day)).isoformat() if use_year else None
        match = re.fullmatch(r'(\d{1,2})/(\d{1,2})(?:/((?:19|20)\d{2}))?', text)
        if match and numeric_order:
            first, second, explicit_year = match.groups()
            day, month = (int(first), int(second)) if numeric_order == 'DMY' else (int(second), int(first))
            use_year = int(explicit_year) if explicit_year else year
            return date(use_year, month, day).isoformat() if use_year else None
    except (ValueError, TypeError):
        pass
    return None


def weekday(text):
    words = set(re.findall(r'[a-z]+', str(text).lower()))
    matches = [number for number, names in enumerate(WEEKDAYS) if words.intersection(names)]
    return matches[0] if len(matches) == 1 else None


def event_keys(text, numbered_column=False):
    text = str(text)
    keys, explicit = [], set()
    for prefix, pattern in [('class-test', r'(?:class\s*test|klastoets)'),
                            ('weekly-test', r'(?:weekly\s*test|weeklikse\s*toets|weektoets)')]:
        for value in re.findall(r'\b' + pattern + r'\s*(\d+)\b(?!\.\d)', text, re.I):
            keys.append(f'{prefix}-{int(value)}')
            explicit.add(int(value))
    for value in re.findall(r'\b(?:test|toets)\s*(\d+)\b(?!\.\d)', text, re.I):
        if int(value) not in explicit:
            keys.append(f'test-{int(value)}')
    if numbered_column and re.fullmatch(r'\s*\d+\s*', text):
        keys.append(f'test-{int(text)}')
    keys.extend('aleks-' + str(int(value)) for value in re.findall(r'\baleks\s*(\d+)\b', text, re.I))
    if re.search(r'\b(?:wik|mic)\b', text, re.I):
        keys.append('mic-1')
    return sorted(set(keys))


def analyze_rows(rows, filename):
    """Return source-linked context only for recognized date/content tables."""
    header_index = None
    compact = False
    use_rows = rows
    def columns(header):
        names = [' '.join(str(value).lower().split()) for value in header]
        find = lambda pattern: next((i for i, name in enumerate(names) if re.search(pattern, name)), None)
        return {'date': find(r'\b(?:datum|date)\b'), 'day': find(r'\b(?:dag|day)\b'),
                'week': find(r'\bweek\b'), 'period': find(r'\b(?:period|periode|time|tyd)\b'),
                'content': find(r'\b(?:content|inhoud|topic|onderwerp|study section|leerafdeling|assessment|toets|test)\b')}
    for index, row in enumerate(rows[:3]):
        cols = columns(row)
        if cols['date'] is not None and cols['content'] is not None:
            header_index = index
            header = [cell for cell in row if str(cell).strip()]
            body = [[cell for cell in item if str(cell).strip()] for item in rows[index + 1:] if any(str(cell).strip() for cell in item)]
            if len(header) < len(row) and body and all(len(item) == len(header) for item in body):
                compact = True
                use_rows = [[cell for cell in item if str(cell).strip()] for item in rows]
                cols = columns(use_rows[index])
            break
    if header_index is None:
        return None
    title = ' '.join(str(cell) for row in rows[:header_index] for cell in row)
    year = source_year(title + ' ' + filename)
    group = re.search(r'\(([^()]+)\)', title)
    group = group.group(1) if group else None
    numeric = set()
    for row in use_rows[header_index + 1:]:
        if cols['date'] >= len(row):
            continue
        match = re.fullmatch(r'(\d{1,2})/(\d{1,2})(?:/\d{4})?', str(row[cols['date']]).strip())
        if match:
            first, second = map(int, match.groups())
            if first > 12 >= second:
                numeric.add('DMY')
            elif second > 12 >= first:
                numeric.add('MDY')
    order = next(iter(numeric)) if len(numeric) == 1 else None
    contexts = []
    last_date = last_date_row = last_week = active_day = None
    def cell(row, name):
        index = cols[name]
        return str(row[index]).strip() if index is not None and index < len(row) else ''
    numbered = cols['period'] is None and re.search(r'\b(?:test|toets|assessment)\b', str(use_rows[header_index][cols['content']]), re.I)
    for index, row in enumerate(use_rows):
        if index <= header_index:
            contexts.append(None)
            continue
        raw_date, day_text, week = cell(row, 'date'), cell(row, 'day'), cell(row, 'week')
        declared_day = weekday(day_text)
        current_date = parsed_date(raw_date, year, order) if raw_date else None
        state, origins, possible = 'unknown', [], []
        if current_date:
            state, origins = 'explicit', [index]
            check_day = declared_day if declared_day is not None else active_day
            if check_day is not None and date.fromisoformat(current_date).weekday() != check_day:
                possible, current_date, state = [current_date], None, 'ambiguous'
            else:
                last_date, last_date_row = current_date, index
        elif (not raw_date and last_date and (cols['period'] is not None or cols['day'] is not None)
              and (not week or week == last_week)):
            if declared_day is None or date.fromisoformat(last_date).weekday() == declared_day:
                current_date, state, origins = last_date, 'inherited', [last_date_row]
            else:
                state = 'ambiguous'
                # A following merged date is evidence for review, not permission
                # to silently move a test from the preceding Tuesday to Wednesday.
                for following in use_rows[index + 1:index + 3]:
                    candidate = parsed_date(cell(following, 'date'), year, order)
                    if candidate and date.fromisoformat(candidate).weekday() == declared_day:
                        possible.append(candidate)
                        break
                last_date = last_date_row = None
        if raw_date and not current_date:
            last_date = last_date_row = None
        if week:
            last_week = week
        if declared_day is not None:
            active_day = declared_day
        elif day_text:  # Recess/assessment notices break inheritance.
            last_date = last_date_row = active_day = None
            current_date, state = None, 'unknown'
        period = cell(row, 'period')
        times = re.fullmatch(r'(\d{1,2}):([0-5]\d)\s*[-–—]\s*(\d{1,2}):([0-5]\d)', period)
        start = end = None
        if times and all(int(times.group(number)) < 24 for number in (1, 3)):
            start = f'{int(times.group(1)):02}:{times.group(2)}'
            end = f'{int(times.group(3)):02}:{times.group(4)}'
        content = cell(row, 'content')
        contexts.append({'date': current_date, 'date_state': state, 'date_source_rows': origins,
            'possible_dates': sorted(set(possible)), 'period_start': start, 'period_end': end,
            'event_keys': event_keys(content, bool(numbered)), 'group': group,
            'session_only': bool(re.search(r'\b(?:tut|tutorial|tutoriaal)\b', content, re.I))})
    return {'rows': contexts, 'columns': [str(value) for value in use_rows[header_index]], 'compacted': compact}


def enrich_sections(blocks, max_bytes=2500):
    """Reconstruct split tables losslessly, then attach original-row context."""
    result = [dict(block) for block in blocks]
    groups = {}
    for block in result:
        if block.get('type') != 'table':
            continue
        try:
            rows = json.loads(block['content'])['rows']
            if not rows or not all(isinstance(row, list) for row in rows):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        parent = re.sub(r'-part\d+$', '', block['id'])
        groups.setdefault((block['source_file'], block['page'], parent), []).append((block, rows))
    for chunks in groups.values():
        original, mappings = [], []
        for block, rows in chunks:
            if not original:
                original = list(rows)
                indices = list(range(len(rows)))
            else:
                overlap = (len(rows) >= 3 and rows[1] == original[-1] and
                    len(json.dumps({'rows': [original[0], original[-1], rows[2]]}, ensure_ascii=False).encode()) <= max_bytes)
                tail = rows[2:] if overlap else rows[1:]
                indices = [0] + ([len(original) - 1] if overlap else []) + list(range(len(original), len(original) + len(tail)))
                original.extend(tail)
                if [original[index] for index in indices] != rows:
                    raise ValueError('Table split provenance could not be reconstructed')
            mappings.append(indices)
        analysis = analyze_rows(original, chunks[0][0]['source_file'])
        if analysis:
            for (block, _), indices in zip(chunks, mappings):
                block['row_context'] = [analysis['rows'][index] for index in indices]
                block['table_columns'] = analysis['columns']
                block['original_row_indices'] = indices
    return result


def schedule_candidates(blocks):
    """Expose source session windows separately from exact assessment start times."""
    result, seen = [], set()
    for block in blocks:
        for row, context in enumerate(block.get('row_context', [])):
            if not context or not context['event_keys']:
                continue
            original_row = block['original_row_indices'][row]
            parent = re.sub(r'-part\d+$', '', block['id'])
            for event in context['event_keys']:
                identity = (block['source_file'], block['page'], parent, original_row, event)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append({'event_key': event, 'date': context['date'], 'date_state': context['date_state'],
                    'possible_dates': context['possible_dates'], 'group': context['group'],
                    'session_start': context['period_start'], 'session_end': context['period_end'],
                    'session_only': context['session_only'],
                    'source': {'block': block['id'], 'row': row, 'original_row': original_row,
                               'file': block['source_file'], 'page': block['page']}})
    return result


def mentioned_dates(text, year=None):
    """Literal named/ISO dates only; ambiguous numeric prose is not guessed."""
    result = set()
    def add(day, month, explicit_year):
        use_year = int(explicit_year) if explicit_year else year
        if use_year:
            try:
                result.add(date(use_year, MONTH_INDEX[month.lower()], int(day)).isoformat())
            except (ValueError, KeyError):
                pass
    for value in re.findall(r'\b(?:19|20)\d{2}-\d{2}-\d{2}\b', text):
        try:
            result.add(date.fromisoformat(value).isoformat())
        except ValueError:
            pass
    pattern = r'\b(\d{1,2})\s*[- ]\s*(' + MONTH_WORDS + r')\.?(?:\s*[- ,]?\s*((?:19|20)\d{2}))?\b'
    for day, month, explicit_year in re.findall(pattern, text, re.I):
        add(day, month, explicit_year)
    for first, last, month, explicit_year in re.findall(
            r'\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+(' + MONTH_WORDS + r')\.?(?:\s+((?:19|20)\d{2}))?\b', text, re.I):
        add(first, month, explicit_year)
        add(last, month, explicit_year)
    return result
