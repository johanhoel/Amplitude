"""Self-test before a restart:  python3 -m homedeck.check   (homedeck-apply and the editor run this).

Checks, without starting anything: every module compiles and imports, and homedeck.toml is valid.
Exit code 0 = safe to restart; 1 = do NOT restart (the reasons are printed, with file and line).
"""
import importlib, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ['config', 'store', 'auth', 'devices', 'studio', 'ha', 'presence', 'notify', 'home', 'leave', 'insights', 'layouts', 'transit', 'weather',
           'news', 'audio', 'links', 'status', 'web', 'main']


def main():
    os.environ['HOMEDECK_READONLY'] = '1'
    problems = []
    files = [os.path.join(HERE, f) for f in sorted(os.listdir(HERE)) if f.endswith('.py')]
    files += [p for p in [os.path.join(os.path.dirname(HERE), 'server.py')] if os.path.exists(p)]
    for path in files:                                 # syntax: compiled in memory, nothing is written
        try:
            with open(path, encoding='utf-8') as fh:
                compile(fh.read(), path, 'exec')
        except SyntaxError as e:
            problems.append(f'{os.path.basename(path)} line {e.lineno}: {e.msg}' + (f'  ->  {e.text.strip()}' if e.text else ''))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            problems.append(f'{os.path.basename(path)}: {e}')
    os.environ['HOMEDECK_CHECKONLY'] = '1'
    from homedeck import config
    tree, errs = config.read(config.CONFIG_FILE)
    problems += [f'homedeck.toml: {e}' for e in errs]
    if not problems:                                   # only import when everything compiles (imports run module code)
        os.environ['HOMEDECK_NO_BACKGROUND'] = '1'
        del os.environ['HOMEDECK_CHECKONLY']
        importlib.reload(config)
        for m in MODULES:
            try:
                importlib.import_module('homedeck.' + m)
            except SystemExit as e:
                problems.append(f'{m}.py: {e}')
            except Exception:
                tb = traceback.extract_tb(sys.exc_info()[2])[-1]
                problems.append(f'{m}.py: {sys.exc_info()[1]!r} (at {os.path.basename(tb.filename)} line {tb.lineno})')
    if problems:
        print('NOT OK - do not restart:\n  ' + '\n  '.join(problems))
        return 1
    print(f'OK - {len(MODULES)} modules and homedeck.toml checked')
    return 0


if __name__ == '__main__':
    sys.exit(main())
