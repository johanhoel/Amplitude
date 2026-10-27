"""Start Home Deck: the background jobs, then the web server.

HOMEDECK_PORT overrides [server] port; HOMEDECK_NO_BACKGROUND=1 starts only the web server (a test copy next to
the real one must not send presence to Home Assistant or ntfy notices twice); HOMEDECK_PREVIEW=1 (the editor's
live preview of an unsaved backend file) also runs the read-only status refresh.
"""
import os, sys, threading
from http.server import ThreadingHTTPServer

from . import leave, presence, status, studio
from .config import C, REPORT
from .web import Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return                                     # a page closed while loading: not an error worth a traceback
        super().handle_error(request, client_address)


def run():
    if not REPORT['ok']:
        print('settings problems (running on ' + REPORT['using'] + '):\n  ' + '\n  '.join(REPORT['problems']), flush=True)
    if os.environ.get('HOMEDECK_NO_BACKGROUND') == '1':
        jobs = ()
    elif os.environ.get('HOMEDECK_PREVIEW') == '1':    # editor preview copy: only read-only status refresh, no presence/notices
        jobs = (status.refresher,)
    else:
        jobs = (status.refresher, presence.presence_loop, presence.camera_trigger_loop, leave.leave_watch_loop, studio.watch_loop)
    for job in jobs:
        threading.Thread(target=job, name=job.__name__, daemon=True).start()
    port = int(os.environ.get('HOMEDECK_PORT') or C.PORT)
    print(f'Home Deck listening on :{port}', flush=True)
    Server(('0.0.0.0', port), Handler).serve_forever()
