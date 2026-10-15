"""Claude's handle on the owner's open park editor (the live channel in server.py).

    from cpe_client import Editor
    ed = Editor()                       # http://127.0.0.1:8914 by default; tests use Editor(8905)
    ed.view()                           # what the owner is looking at: camera, selection, hover, on-screen pieces
    ed.snapshot()                       # PNG of their exact screen -> path
    ed.edit(lambda park: ..., 'label')  # change park.json; their editor reloads it at once (they can undo)
    ed.cmd('select', ids=['p12'])       # drive their view: select, selectLine, frame, view, camera, solo, show, toast, ...
"""
import json, time, urllib.request, urllib.error, uuid


class Editor:
    def __init__(self, port=8914):
        self.base = f'http://127.0.0.1:{port}/'

    def _req(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        r = urllib.request.Request(self.base + path, data=data, headers={'Content-Type': 'application/json'})
        for attempt in range(4):      # the Mac can be busy with builds: retry a stalled connection
            try:
                with urllib.request.urlopen(r, timeout=8) as f:
                    return json.loads(f.read())
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    return {'conflict': True, **json.loads(e.read())}
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(1)

    def park(self):
        return self._req('api/park')

    def save(self, park, label=''):
        return self._req('api/save', {'park': park, 'base_rev': park['rev'], 'label': label, 'by': 'claude'})

    def edit(self, fn, label='', tries=5):
        """fn(park) mutates the park in place. Retries when the owner saved in between."""
        for _ in range(tries):
            p = self.park()
            fn(p)
            r = self.save(p, label)
            if not r.get('conflict'):
                return r
            time.sleep(1.5)        # the owner's autosave landed first: reload and redo
        raise RuntimeError('park kept changing; try again')

    def cmd(self, op, to='active', **kw):
        return self._req('api/cmd', {'op': op, 'to': to, **kw})

    def lock(self, text='', seconds=600):
        """View-only mode in the owner's editor while I edit (expires by itself)."""
        return self.cmd('lock', text=text, seconds=seconds)

    def unlock(self, text=''):
        return self.cmd('unlock', text=text)

    def reload(self, relock=None, wait=10):
        """Reload the owner's page for new editor code and re-apply a lock (the page keeps its view itself)."""
        v = self.view()
        if v and v.get('unsaved'):
            raise RuntimeError('owner has unsaved edits; not reloading')
        self.cmd('reload'); time.sleep(wait)      # the page restores its own camera, solo and selection
        if relock is not None:
            self.lock(relock)

    def view(self, all_tabs=False):
        v = self._req('api/viewstate')
        return v if all_tabs else v.get('active')

    def snapshot(self, timeout=15):
        req = 'snap-' + uuid.uuid4().hex[:8]
        self.cmd('snapshot', req=req)
        t = time.time()
        while time.time() - t < timeout:
            r = self._req(f'api/snapshot?req={req}')
            if r.get('ready'):
                return r['file']
            time.sleep(0.5)
        raise TimeoutError('no editor answered (is the page open?)')


if __name__ == '__main__':
    import sys
    ed = Editor(int(sys.argv[1]) if len(sys.argv) > 1 else 8914)
    print(json.dumps(ed.view(), indent=1))
