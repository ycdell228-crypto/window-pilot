"""Full owned headless MCP task plus read-only desktop event/sampling evidence."""
import base64
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from window_pilot.service import Service
from window_pilot.rpc import Dispatcher
from window_pilot.coordination import Coordinator

spec = importlib.util.spec_from_file_location('owned_process_helpers', ROOT / 'scripts/accept-browser-crash.py')
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)
OUT = ROOT / '.local/browser-noninterference'; OUT.mkdir(parents=True, exist_ok=True)
U = C.WinDLL('user32', use_last_error=True)
HOOK = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)
ENUM = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
for name, args, ret in [
    ('SetWinEventHook', [W.DWORD,W.DWORD,W.HMODULE,HOOK,W.DWORD,W.DWORD,W.DWORD], W.HANDLE),
    ('UnhookWinEvent', [W.HANDLE], W.BOOL), ('GetForegroundWindow', [], W.HWND),
    ('GetWindowThreadProcessId', [W.HWND,C.POINTER(W.DWORD)], W.DWORD),
    ('GetCursorPos', [C.POINTER(W.POINT)], W.BOOL), ('IsWindowVisible', [W.HWND], W.BOOL),
    ('EnumWindows', [ENUM,W.LPARAM], W.BOOL),
    ('PeekMessageW', [C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT], W.BOOL),
]:
    fn=getattr(U,name); fn.argtypes=args; fn.restype=ret


def pid_for(hwnd):
    pid=W.DWORD(); U.GetWindowThreadProcessId(hwnd,C.byref(pid)); return pid.value


def main():
    posts=[]; events=[]; samples=[]; visible=[]; tracked={}; transports=[]
    stop=threading.Event(); ready=threading.Event(); hook_state={}
    class Page(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self):
            body=b'<!doctype html><title>Owned MCP noninterference</title><h1>Owned local form</h1><form action="/submit" method="post"><label>Name<input name="name"></label><button>Submit once</button></form>'
            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            posts.append(self.rfile.read(int(self.headers['Content-Length'])).decode())
            self.send_response(200); self.end_headers(); self.wfile.write(b'<h1>Submitted exactly once: final task value</h1>')
    server=ThreadingHTTPServer(('127.0.0.1',0),Page)
    server_thread=threading.Thread(target=server.serve_forever); server_thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    cfg=OUT/'config.json'
    cfg.write_text(json.dumps({'browser':{'enabled':True,'node':support.CONFIG['node'],'executable':support.CONFIG['browser'],
        'playwright':support.CONFIG['playwright'],'allowed_origins':[origin]},
        'authorization':{'mode':'enforced','grants':[{'id':'own-noninterference',
            'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
            'access':['browser'],'origins':[origin]}]}}))
    service=Service(cfg,OUT/'executor.lock',coordinator=Coordinator(),connection_id='owned-noninterference')
    dispatcher=Dispatcher(service); calls=[]; seq=0
    def monitor():
        @HOOK
        def foreground(hook,event,hwnd,obj,child,tid,stamp):
            if hwnd: events.append({'time':time.monotonic(),'hwnd':int(hwnd),'pid':pid_for(hwnd),'event':event})
        @ENUM
        def visit(hwnd,_):
            if U.IsWindowVisible(hwnd): visible.append({'time':time.monotonic(),'hwnd':int(hwnd),'pid':pid_for(hwnd)})
            return True
        hook=U.SetWinEventHook(3,3,None,foreground,0,0,0)
        hook_state['installed']=bool(hook); ready.set()
        if not hook: return
        msg=W.MSG()
        try:
            while not stop.is_set():
                while U.PeekMessageW(C.byref(msg),None,0,0,1):
                    U.TranslateMessage(C.byref(msg)); U.DispatchMessageW(C.byref(msg))
                for t in list(service.browser.sessions.values()):
                    if t not in transports: transports.append(t)
                for t in transports: support.capture(t.process.pid,tracked)
                front=U.GetForegroundWindow(); point=W.POINT(); ok=U.GetCursorPos(C.byref(point))
                samples.append({'time':time.monotonic(),'hwnd':int(front or 0),'pid':pid_for(front) if front else 0,
                    'cursor':[point.x,point.y] if ok else None})
                U.EnumWindows(visit,0)
                stop.wait(.01)
        except Exception as e:
            hook_state['error']=repr(e)
        finally:
            hook_state['unhooked']=bool(U.UnhookWinEvent(hook))
    monitor_thread=threading.Thread(target=monitor); monitor_thread.start()
    assert ready.wait(3) and hook_state['installed']
    def call(**args):
        nonlocal seq
        seq+=1
        reply=dispatcher.handle({'jsonrpc':'2.0','id':seq,'method':'tools/call',
            'params':{'name':'browser_session','arguments':args}})['result']
        assert not reply['isError'],reply['content'][0]
        val=json.loads(reply['content'][0]['text'])
        for block in reply['content'][1:]:
            if block['type']=='image': (OUT/f'{seq}.png').write_bytes(base64.b64decode(block['data']))
        calls.append({'operation':args['operation'],'action':args.get('action'),'result':val})
        return val
    started=time.monotonic(); succeeded=False
    try:
        state=call(operation='begin',url=origin,purpose='owned full headless task with passive interference monitoring')
        sid=state['session_id']
        for value in ['first task value','second task value','final task value']:
            time.sleep(1.2)
            node=next(n for n in state['result']['state']['nodes'] if n['name']=='Name')
            state=call(operation='step',session_id=sid,control_id=node['control_id'],action='set_value',value=value)
            assert next(n['value'] for n in state['result']['state']['nodes'] if n['name']=='Name')==value
        time.sleep(1.2)
        node=next(n for n in state['result']['state']['nodes'] if n['name']=='Submit once')
        state=call(operation='step',session_id=sid,control_id=node['control_id'],action='click')
        assert posts==['name=final+task+value'],posts
        assert 'Submitted exactly once: final task value' in state['result']['state']['document_text']
        time.sleep(1.2)
        state=call(operation='observe',session_id=sid)
        assert 'Submitted exactly once: final task value' in state['result']['state']['document_text']
        assert call(operation='end',session_id=sid)['worker_exited']
        succeeded=True
    finally:
        service.dispose(); time.sleep(.2); stop.set(); monitor_thread.join(5)
        server.shutdown(); server.server_close(); server_thread.join(3)
        target=set(tracked)
        matched_events=[x for x in events if x['pid'] in target]
        matched_front=[x for x in samples if x['pid'] in target]
        matched_visible=[x for x in visible if x['pid'] in target]
        exited={str(pid):support.K.WaitForSingleObject(row['handle'],5000)==0 for pid,row in tracked.items()}
        process_rows=[{k:v for k,v in row.items() if k!='handle'} for row in tracked.values()]
        for row in tracked.values(): support.K.CloseHandle(row['handle'])
        report={'task_succeeded':succeeded,'duration_seconds':time.monotonic()-started,'samples':len(samples),
            'foreground_target_samples':matched_front,'foreground_target_events':matched_events,'visible_target_windows':matched_visible,
            'foreground_available_samples':sum(bool(x['hwnd']) for x in samples),
            'foreground_changes_unknown':sum(a['hwnd']!=b['hwnd'] for a,b in zip(samples,samples[1:])),
            'cursor_changes_unknown':sum(a['cursor']!=b['cursor'] for a,b in zip(samples,samples[1:])),
            'processes':process_rows,'all_captured_handles_signaled':exited,'posts':posts,'hook':hook_state,
            'monitor_thread_exited':not monitor_thread.is_alive(),'server_thread_exited':not server_thread.is_alive(),
            'worker_cleanup_complete':[t.cleanup_complete() for t in transports],
            'scope':'Current isolated headless browser MCP path only. Foreground/cursor changes have no attribution; no real-user typing or arbitrary Windows application certification.'}
        (OUT/'results.json').write_text(json.dumps(report,indent=2))
        (OUT/'observations.json').write_text(json.dumps({'samples':samples,'foreground_events':events,'visible_windows':visible},indent=2))
        (OUT/'mcp-calls.json').write_text(json.dumps(calls,indent=2))
    assert succeeded and len(samples)>100 and report['foreground_available_samples']>0,report
    assert not matched_events and not matched_front and not matched_visible,report
    assert all(exited.values()) and all(report['worker_cleanup_complete'])
    assert hook_state.get('unhooked') and 'error' not in hook_state
    assert report['monitor_thread_exited'] and report['server_thread_exited']
    print(json.dumps(report))


if __name__=='__main__': main()
