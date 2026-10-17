"""Exercise real ordinary Python children under the existing guards, never native workloads."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from atelier.harness.safety.cancellation import termination_cleanup


def test_termination_unwinds_once_and_restores_handlers():
    before = signal.getsignal(signal.SIGTERM)
    events = []
    with pytest.raises(SystemExit) as error:
        with termination_cleanup():
            try:
                signal.raise_signal(signal.SIGTERM)
            finally:
                events.append('cleanup')
                signal.raise_signal(signal.SIGTERM)
                events.append('finished')
    assert error.value.code == 143
    assert events == ['cleanup','finished']
    assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.skipif(sys.platform != 'darwin', reason='actual macOS process and aggregate guards')
@pytest.mark.parametrize('mode',['controller-term','controller-kill','group-term','group-kill'])
def test_outer_interruption_leaves_independent_cleanup_receipt(tmp_path, mode):
    from atelier.harness import capacity_protocol as wire
    folder = tmp_path / 'guard'
    script = """
import sys
from atelier.harness.safety.guarded import run
run([sys.executable,'-c','import time; time.sleep(60)'],sys.argv[1],
    timeout=30,lock=False,kind='compile',aggregate_tree=True)
"""
    # Isolate test configuration; no machine client, render locks or broker is altered.
    env = {k:v for k,v in os.environ.items() if not k.startswith('ATELIER_')}
    env['HOME'] = str(tmp_path)
    with (tmp_path/'launcher.log').open('w') as log:
        launcher = subprocess.Popen([sys.executable,'-c',script,str(folder)],env=env,
                                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    child = None
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            p=folder/'memory-health-tree.json'
            if p.exists():
                try: receipt=json.loads(p.read_text())
                except ValueError:continue
                if receipt.get('state')=='running':
                    child=(receipt['owner'],receipt['owner_started']);break
            if launcher.poll() is not None:break
            time.sleep(.02)
        assert child is not None,(tmp_path/'launcher.log').read_text()
        sig=signal.SIGKILL if mode.endswith('kill') else signal.SIGTERM
        if mode.startswith('group'):os.killpg(launcher.pid,sig)
        else:launcher.send_signal(sig)
        assert launcher.wait(timeout=15)!=0
        deadline=time.monotonic()+8
        receipt={}
        while time.monotonic()<deadline:
            receipt=json.loads((folder/'memory-health-tree.json').read_text())
            if receipt.get('cleanup_complete'):break
            time.sleep(.02)
        assert receipt.get('cleanup_complete') is True,receipt
        assert receipt['state'] in ('child_exited','controller_exited'),receipt
        samples=receipt.get('cleanup_processes',receipt['processes'])
        total=receipt.get('cleanup_footprint_bytes',receipt['footprint_bytes'])
        assert samples==[] and total==0
        assert not wire.live(child)
        if mode=='controller-kill':assert receipt['state']=='controller_exited'
        assert not list(folder.glob('*success*'))
    finally:
        if launcher.poll() is None:
            launcher.kill();launcher.wait(timeout=5)
        if child is not None and wire.live(child):
            os.kill(child[0],signal.SIGKILL)


@pytest.mark.skipif(sys.platform != 'darwin', reason='real macOS guard processes and kernel exit watches')
@pytest.mark.parametrize('kill_monitor',[False,True])
def test_private_broker_releases_controller_loss_only_with_surviving_cleanup_monitor(tmp_path,kill_monitor):
    from contextlib import contextmanager
    import tempfile
    import threading
    from atelier.harness import capacity_broker as server, capacity_client as client
    from atelier.harness import capacity_protocol as wire
    from atelier.harness.capacity import Resources
    folder=tmp_path/'job'
    script="""
import contextlib,json,sys
from atelier.harness.safety import guarded
from atelier.harness.capacity_client import AdmissionSession
@contextlib.contextmanager
def isolated_lock(*args,**kwargs):
    yield
# Only this private-broker sleeping-Python fixture skips the machine's real native locks.
guarded.render_lock=isolated_lock
s=AdmissionSession(sys.argv[1],json.loads(sys.argv[3]))
guarded.run([sys.executable,'-c','import time;time.sleep(60)'],sys.argv[2],
    timeout=30,kind='compile',admission=s,aggregate_tree=True)
"""
    with tempfile.TemporaryDirectory(prefix='acancel-',dir='/tmp') as short:
        broker=server.CapacityBroker(Path(short)/'broker',disk_pool=Path(short),total=Resources(memory_mib=32768,cpu_millis=8000),
            observe=lambda:{'observed_monotonic':time.monotonic(),'available_memory_mib':32768})
        thread=threading.Thread(target=broker.serve_forever,daemon=True);thread.start()
        request=dict(id='cancel-fixture',resources=dict(memory_mib=10240,cpu_millis=1000,temp_mib=0,io_slots=0,gpu_mib=0),
                     locks=['private-fixture'],seconds=1,performance=True)
        env={k:v for k,v in os.environ.items() if not k.startswith('ATELIER_')};env['HOME']=str(tmp_path)
        with (tmp_path/'broker-launch.log').open('w') as log:
            launcher=subprocess.Popen([sys.executable,'-c',script,str(broker.socket_path),str(folder),json.dumps(request)],
                env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        child=None
        try:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with broker._lock:
                    state=broker._load();r=state['records'].get('cancel-fixture')
                    if r and r['state']=='running':
                        # Force the historical discovery gap from the incident: retained exits alone cannot release.
                        r['ancestry_unknown']=True;broker._save(state)
                        child=tuple(r['child']);monitor=(r['guards']['tree_guard']['pid'],r['guards']['tree_guard']['start']);break
                    broker.connection.rollback()
                if launcher.poll() is not None:break
                time.sleep(.02)
            assert child is not None,(tmp_path/'broker-launch.log').read_text()
            if kill_monitor:os.kill(monitor[0],signal.SIGKILL)
            launcher.send_signal(signal.SIGTERM if kill_monitor else signal.SIGKILL)
            assert launcher.wait(timeout=15)!=0
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                status=client.status(broker.socket_path)
                if not kill_monitor and status['charged_count']==0:break
                if kill_monitor and not wire.live(child):break
                time.sleep(.02)
            if kill_monitor:
                assert client.reconcile(broker.socket_path)['charged_count']==1
                assert json.loads((folder/'memory-health-tree.json').read_text())['state']=='running'
            else:
                assert status['charged_count']==0 and status['recovering'] is False
                receipt=json.loads((folder/'memory-health-tree.json').read_text())
                assert receipt['state']=='controller_exited' and receipt['cleanup_complete']
                with broker._lock:
                    state=broker._load();r=state['records']['cancel-fixture'];broker.connection.rollback()
                assert r['release_witness']['kind']=='guarded-tree-stop'
            assert not wire.live(child)
        finally:
            if launcher.poll() is None:launcher.kill();launcher.wait(timeout=5)
            if child is not None and wire.live(child):os.kill(child[0],signal.SIGKILL)
            broker._stop.set();thread.join(timeout=3);broker.close()



@pytest.mark.parametrize('old_group,controller', [(True,[1,10]),(False,None),(False,[2,20])])
def test_old_or_mismatched_supervision_refuses_before_go(tmp_path,old_group,controller):
    from atelier.harness import capacity_protocol as wire
    report=tmp_path/'tree.json';report.write_text(json.dumps({'controller':controller}))
    guards=dict(process_guard=dict(pid=11,start=110,report=str(report)),tree_guard=dict(pid=12,start=120,report=str(report)))
    with pytest.raises(wire.CapacityError,match='supervision'):
        wire.require_independent_guards(guards,(1,10),started=lambda pid:pid*10,
                                       group=lambda pid:1 if old_group else pid)


def test_independent_guards_bind_the_original_controller(tmp_path):
    from atelier.harness import capacity_protocol as wire
    report=tmp_path/'tree.json';report.write_text(json.dumps({'controller':[1,10]}))
    guards=dict(process_guard=dict(pid=11,start=110,report=str(report)),tree_guard=dict(pid=12,start=120,report=str(report)))
    wire.require_independent_guards(guards,(1,10),started=lambda pid:pid*10,group=lambda pid:pid)
