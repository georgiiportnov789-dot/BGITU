"""Разбор файла расписания БГИТУ (.xls/.xlsx) в занятия."""
import re

WEEKDAYS = {
    'понедельник': 1, 'вторник': 2, 'среда': 3, 'четверг': 4, 'пятница': 5, 'суббота': 6,
}
TIME_RE = re.compile(r'^\s*\d{1,2}[.:]\d{2}\s*[-–—]\s*\d{1,2}[.:]\d{2}\s*$')


def normalize_time(value):
    value = value.strip().replace('.', ':')
    found = re.match(r'^(\d{1,2}):(\d{2})$', value)
    return f'{int(found.group(1))}:{found.group(2)}' if found else value
GROUP_RE = re.compile(r'^[А-ЯЁA-Z]{2,6}\s*-\s*\d{2,3}$')


def cell_text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return str(value).replace('\xa0', ' ').replace('\r', '\n').strip()


def read_rows(path):
    """Вернуть (строки, объединённые диапазоны) в 0-индексах, rhi/chi исключающие."""
    if path.lower().endswith('.xls'):
        import xlrd

        book = xlrd.open_workbook(path, formatting_info=True)
        sheet = book.sheet_by_index(0)
        rows = [[cell_text(sheet.cell_value(r, c)) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        return rows, list(sheet.merged_cells)

    from openpyxl import load_workbook

    book = load_workbook(path, data_only=True, read_only=False)
    sheet = book.worksheets[0]
    rows = [
        [cell_text(sheet.cell(row=r, column=c).value) for c in range(1, sheet.max_column + 1)]
        for r in range(1, sheet.max_row + 1)
    ]
    merged = [(m.min_row - 1, m.max_row, m.min_col - 1, m.max_col) for m in sheet.merged_cells.ranges]
    return rows, merged


def group_columns(rows, merged):
    """Колонки групп: {col: (код группы, подгруппа)} из шапки и строки подгрупп."""
    columns = {}
    header = 1
    if len(rows) <= header:
        return columns
    for rlo, rhi, clo, chi in merged:
        if rlo <= header < rhi and clo >= 3:
            text = rows[header][clo] if clo < len(rows[header]) else ''
            if GROUP_RE.match(text):
                for col in range(clo, chi):
                    sub = rows[2][col] if len(rows) > 2 and col < len(rows[2]) else ''
                    columns[col] = (text.strip().upper(), sub.strip().lower())
    for col, text in enumerate(rows[header]):
        if col < 3 or col in columns:
            continue
        if GROUP_RE.match(text):
            sub = rows[2][col] if len(rows) > 2 and col < len(rows[2]) else ''
            columns[col] = (text.strip().upper(), sub.strip().lower())
    return columns


def parse_cell(text):
    """'Физика \\n314 (Симохин С.П.)' → subject/room/teacher."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return None
    flat = ' '.join(lines)
    teacher = ''
    found = re.search(r'\(([^()]{2,90})\)\s*$', flat)
    if found:
        teacher = found.group(1).strip()
        flat = flat[: found.start()].strip()

    room = ''
    found = re.search(r'№\s*([0-9]{1,4}[а-яА-Я]?)', flat)
    if found:
        room = found.group(1).strip()
        flat = flat[: found.start()].strip()
    elif re.search(r'\bДОТ\b', flat):
        room = 'ДОТ'
        flat = re.sub(r'\bДОТ\b', '', flat).strip()
    elif re.search(r'\bДО\b', flat):
        room = 'ДО'
        flat = re.sub(r'\bДО\b', '', flat).strip()
    else:
        found = re.search(r'(?:^|\s)([0-9]{2,4}[а-яА-Я]?)\s*$', flat)
        if found:
            room = found.group(1)
            flat = flat[: found.start()].strip()

    subject = re.sub(r'\s+', ' ', flat).strip(' -–—.,')
    if len(subject) < 2:
        return None
    low = subject.lower()
    kind = ''
    if 'лекц' in low:
        kind = 'лекция'
    elif 'лаборатор' in low or re.search(r'\bлаб\.', low):
        kind = 'лабораторная'
    elif 'практи' in low or 'семинар' in low:
        kind = 'практика'
    elif 'консультац' in low:
        kind = 'консультация'
    return {'subject': subject, 'room': room, 'teacher_name': teacher, 'kind': kind}


def parse_schedule(path):
    """→ (занятия, звонки). Занятие: group, weekday, pair, subject, room, teacher, subgroup, week."""
    rows, merged = read_rows(path)
    columns = group_columns(rows, merged)
    if not columns:
        raise ValueError('В файле не найдена шапка с группами (ожидались коды вида ИСТ-201).')

    day_rows = []
    for index, row in enumerate(rows):
        if not row:
            continue
        name = row[0].strip().lower()
        if name in WEEKDAYS:
            day_rows.append((index, WEEKDAYS[name]))

    lessons = []
    bells = {}
    for order, (day_index, weekday) in enumerate(day_rows):
        day_end = day_rows[order + 1][0] if order + 1 < len(day_rows) else len(rows)
        pair_starts = [
            r for r in range(day_index, day_end)
            if any(TIME_RE.match(rows[r][c]) for c in (1, 2) if c < len(rows[r]))
        ]
        for pair_number, start in enumerate(pair_starts, 1):
            end = pair_starts[pair_number] if pair_number < len(pair_starts) else day_end
            for building, col in (('1', 1), ('2', 2)):
                if col < len(rows[start]) and TIME_RE.match(rows[start][col]):
                    start_time, end_time = [normalize_time(p) for p in re.split(r'[-–—]', rows[start][col])]
                    bells.setdefault((building, pair_number), (start_time, end_time))
            for col, (group_code, subgroup) in columns.items():
                cells = []
                for r in range(start, end):
                    if col < len(rows[r]) and rows[r][col].strip():
                        cells.append(rows[r][col])
                parsed = []
                for text in cells:
                    item = parse_cell(text)
                    if item and item not in parsed:
                        parsed.append(item)
                if not parsed:
                    continue
                for index, item in enumerate(parsed):
                    sub = subgroup
                    if not sub and len(parsed) > 1:
                        sub = str(index + 1)
                    lessons.append({
                        'group': group_code,
                        'weekday': weekday,
                        'pair': pair_number,
                        'week': 'all',
                        'subgroup': sub,
                        **item,
                    })
    if not lessons:
        raise ValueError('В файле не найдено ни одного занятия.')
    return lessons, bells
