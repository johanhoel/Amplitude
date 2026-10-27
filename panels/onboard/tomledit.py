"""Change single values in homedeck.toml without losing its comments or layout.

set_value(text, 'services.piholes', ['192.168.1.2'])   one-line  key = value  inside its [section]; the comment after it stays
set_players(text, [{'entity': ..., 'label': ...}])     replaces the run of [[players]] tables
set_table(text, 'presence.phones', {'anna': [...]})    sets those keys inside [presence.phones]; keys not given stay
Only one-line values are edited; a value that spans lines (rooms.order, apple_tv.commands) is never touched.
"""
import json, re


def fmt(v):
    """Python value -> TOML (strings, ints, bools, lists of those)."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return '[' + ', '.join(fmt(x) for x in v) + ']'
    raise TypeError(f'cannot write {type(v).__name__}')


def _key_re(key):
    q = re.escape(key)
    return rf'(?:{q}|"{q}")'


def _section_span(lines, section):
    """-> (first body line, end) of [section], or None."""
    start = next((i for i, l in enumerate(lines) if re.match(rf'\[\s*{re.escape(section)}\s*\]\s*(#.*)?$', l.strip())), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if re.match(r'\s*\[', lines[j])), len(lines))
    return start + 1, end


def _split_comment(rest):
    """'["a", "b"]   # note' -> ('["a", "b"]', '   # note'), honouring # inside quotes."""
    inq = False
    for i, ch in enumerate(rest):
        if ch == '"' and (i == 0 or rest[i - 1] != '\\'):
            inq = not inq
        elif ch == '#' and not inq:
            j = i
            while j > 0 and rest[j - 1] in ' \t':
                j -= 1
            return rest[:j], rest[j:]
    return rest.rstrip(), ''


def set_value(text, dotted, value):
    section, key = dotted.rsplit('.', 1)
    lines = text.split('\n')
    span = _section_span(lines, section)
    if span is None:
        raise KeyError(f'[{section}] not found')
    for i in range(*span):
        m = re.match(rf'(\s*{_key_re(key)}\s*=\s*)(.*)$', lines[i])
        if m:
            val, comment = _split_comment(m.group(2))
            if val.count('[') != val.count(']'):
                raise ValueError(f'{dotted} spans several lines; not edited')
            lines[i] = m.group(1) + fmt(value) + comment
            return '\n'.join(lines)
    raise KeyError(f'{dotted} not found')


def set_table(text, section, values):
    lines = text.split('\n')
    span = _section_span(lines, section)
    if span is None:
        raise KeyError(f'[{section}] not found')
    start, end = span
    last = start - 1
    for k, v in values.items():
        key = k if re.fullmatch(r'[A-Za-z0-9_-]+', k) else json.dumps(k, ensure_ascii=False)
        for i in range(start, end):
            m = re.match(rf'(\s*{_key_re(k)}\s*=\s*)(.*)$', lines[i])
            if m:
                lines[i] = m.group(1) + fmt(v) + _split_comment(m.group(2))[1]
                last = max(last, i)
                break
        else:
            body_end = end
            while body_end > start and not lines[body_end - 1].strip():
                body_end -= 1
            lines.insert(body_end, f'{key} = {fmt(v)}')
            end += 1
    return '\n'.join(lines)


def set_players(text, players):
    """Replace every [[players]] block (they sit together) with the given list."""
    lines = text.split('\n')
    idx = [i for i, l in enumerate(lines) if l.strip() == '[[players]]']
    if not idx:
        raise KeyError('[[players]] not found')
    end = idx[-1] + 1
    while end < len(lines) and not re.match(r'\s*\[', lines[end]) and (lines[end].strip() and not lines[end].lstrip().startswith('#')):
        end += 1
    block = []
    for p in players:
        block += ['[[players]]', f'entity = {fmt(p["entity"])}', f'label = {fmt(p["label"])}']
    return '\n'.join(lines[:idx[0]] + block + lines[end:])
