"""Opt-in real named-pipe deployment acceptance; restores exact config bytes.

Preparation alone has no effects. Run only after the intended executor deployment.
"""
import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NODE = os.environ.get('WINDOW_PILOT_TEST_NODE', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'))
CHROME = os.environ.get('WINDOW_PILOT_TEST_CHROME', 'C:/Program Files/Google/Chrome/Application/chrome.exe')
PLAYWRIGHT = os.environ.get('WINDOW_PILOT_TEST_PLAYWRIGHT', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'))


def atomic_bytes(path, data):
    temporary = path.with_name(path.name + '.browser-acceptance.tmp')
    with temporary.open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


class Client:
    def __init__(self, command, out, name):
        self.out, self.name, self.seq = out, name, 0
        self.queue = queue.Queue(); self.events = []
        self.stderr = (out / (name + '-stderr.txt')).open('w', encoding='utf8')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr, text=True, encoding='utf8', creationflags=subprocess.CREATE_NO_WINDOW)
        def read():
            try:
                for line in self.process.stdout:
                    try: self.queue.put(json.loads(line))
                    except ValueError: self.queue.put({'invalid_json': True})
            finally: self.queue.put(None)
        self.reader = threading.Thread(target=read, daemon=True); self.reader.start()

    def rpc(self, method, params=None):
        self.seq += 1
        request = {'jsonrpc':'2.0','id':self.seq,'method':method,'params':params or {}}
        self.process.stdin.write(json.dumps(request)+'\n'); self.process.stdin.flush()
        response = self.queue.get(timeout=30)
        assert response and response.get('id') == self.seq and 'error' not in response, response
        return response['result']

    def call(self, name, expect=None, **args):
        reply = self.rpc('tools/call', {'name':name,'arguments':args})
        text = reply['content'][0]['text']
        self.events.append({'tool':name,'operation':args.get('operation'),'error':reply['isError'],'text':text})
        if expect:
            assert reply['isError'] and expect in text, text
            return text
        assert not reply['isError'], text
        for block in reply['content'][1:]:
            if block['type'] == 'image':
                (self.out / f'{self.name}-{self.seq}.png').write_bytes(base64.b64decode(block['data'],validate=True))
        return json.loads(text)

    def close(self):
        try:
            if not self.process.stdin.closed: self.process.stdin.close()
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate(); self.process.wait(timeout=5)
        finally:
            self.reader.join(3); self.stderr.close()
            (self.out / (self.name+'-calls.json')).write_text(json.dumps(self.events,indent=2),encoding='utf8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-file',type=Path,required=True)
    parser.add_argument('--apply-test-config',action='store_true')
    parser.add_argument('--expected-code-sha256')
    args=parser.parse_args()
    if not args.apply_test_config: parser.error('requires --apply-test-config; temporarily adds browser config and restores exact original bytes')
    manifest=json.loads(args.service_file.read_text(encoding='utf-8-sig'))
    project=Path(manifest['project']); config=Path(manifest['config'])
    assert config.resolve().is_relative_to(project.resolve()), 'config outside declared project'
    command=[manifest['python'],'-I','-S',str(project/'scripts/runtime_entry.py'),'bridge','--service-file',str(args.service_file.resolve())]
    out=Path(__file__).resolve().parents[1]/'.local/deployment-test'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    original=config.read_bytes(); original_json=json.loads(original.decode('utf-8-sig'))
    (out/'config-original.bin').write_bytes(original)
    clients=[]; server=None; server_thread=None; changed=False; owned_stop=None; a=None; sid=None; summary={}; posts=[]
    def connect(name):
        client=Client(command,out,name); clients.append(client)
        client.rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'owned-deployment-acceptance','version':'1'}})
        tools=client.rpc('tools/list')['tools']
        assert len(tools)==19 and any(t['name']=='browser_session' for t in tools),[t['name'] for t in tools]
        health=client.call('health'); executor=health['executor']
        assert executor['mode']=='administrator_service' and len(executor['code_sha256'])==64,health
        if args.expected_code_sha256: assert executor['code_sha256']==args.expected_code_sha256,executor
        summary[name]={'tool_names':[t['name'] for t in tools],'executor':executor}
        return client
    try:
        pre=connect('preflight')
        assert pre.call('input_control',operation='status')['stopped'] is False, 'already stopped: refusing automatic resume'
        pre.close(); clients.remove(pre)
        class Page(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(b'<h1>Owned deployment form</h1><form action="/submit" method="post"><label>Name<input name="name"></label><button>Submit once</button></form>')
            def do_POST(self):
                posts.append(self.rfile.read(int(self.headers['Content-Length'])).decode())
                self.send_response(200); self.end_headers(); self.wfile.write(b'<h1>Deployment submitted exactly once</h1>')
        server=ThreadingHTTPServer(('127.0.0.1',0),Page)
        server_thread=threading.Thread(target=server.serve_forever); server_thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        config_json={**original_json,'browser':{'enabled':True,'node':NODE,'executable':CHROME,'playwright':PLAYWRIGHT,'allowed_origins':[origin]}}
        assert config.read_bytes()==original, 'config changed since backup: refusing overwrite'
        test_config_bytes=json.dumps(config_json,ensure_ascii=False,indent=2).encode('utf8')
        atomic_bytes(config,test_config_bytes); changed=True
        summary['test_origin']=origin
        a=connect('owner'); b=connect('other')
        assert a.call('input_control',operation='status')['stopped'] is False,'stop appeared before task'
        state=a.call('browser_session',operation='begin',url=origin,purpose='owned deployed named-pipe browser acceptance')
        sid=state['session_id']
        b.call('browser_session',expect='UNKNOWN_BROWSER_SESSION',operation='observe',session_id=sid)
        node=next(n for n in state['result']['state']['nodes'] if n['name']=='Name')
        state=a.call('browser_session',operation='step',session_id=sid,control_id=node['control_id'],action='set_value',value='deployed acceptance')
        assert next(n['value'] for n in state['result']['state']['nodes'] if n['name']=='Name')=='deployed acceptance'
        node=next(n for n in state['result']['state']['nodes'] if n['name']=='Submit once')
        state=a.call('browser_session',operation='step',session_id=sid,control_id=node['control_id'],action='click')
        assert posts==['name=deployed+acceptance'],posts
        state=a.call('browser_session',operation='observe',session_id=sid)
        assert 'Deployment submitted exactly once' in state['result']['state']['document_text']
        assert a.call('browser_session',operation='end',session_id=sid)['worker_exited']; sid=None
        state=a.call('browser_session',operation='begin',url=origin,purpose='owned deployed idle stop cancellation')
        sid=state['session_id']
        assert b.call('input_control',operation='status')['stopped'] is False,'external stop already active'
        stopped=b.call('input_control',operation='stop')
        assert stopped.get('created_by_this_call') is True, 'external stop won race: refusing ownership or resume'
        owned_stop=stopped['stop_id']
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            status=a.call('browser_session',operation='status',session_id=sid)
            if status.get('process_tree_cleanup_confirmed'): break
            time.sleep(.05)
        assert status['worker_exited'] and status['process_tree_cleanup_confirmed'],status
        assert a.call('browser_session',operation='end',session_id=sid)['worker_exited']; sid=None
        current=b.call('input_control',operation='status')
        assert current['stop_id']==owned_stop, 'stop identity changed: refusing resume'
        assert not b.call('input_control',operation='resume',stop_id=owned_stop,confirmation='user_requested_resume',purpose='explicitly authorized deployment acceptance own stop cleanup')['stopped']
        owned_stop=None
        summary['fresh_final_tool_count']=len(a.rpc('tools/list')['tools']); assert summary['fresh_final_tool_count']==19
        summary['passed']=True
    finally:
        try:
            if a and sid:
                try: a.call('browser_session',operation='end',session_id=sid)
                except Exception as exc: summary['end_cleanup_error']=str(exc)
            if owned_stop:
                # Never restore a stop identity that this acceptance did not create.
                try:
                    current=a.call('input_control',operation='status')
                    if current['stop_id']==owned_stop:
                        a.call('input_control',operation='resume',stop_id=owned_stop,confirmation='user_requested_resume',purpose='explicitly authorized deployment acceptance own stop cleanup')
                    else: summary['own_stop_not_resumed']='current stop identity differs'
                except Exception as exc: summary['own_stop_cleanup_error']=str(exc)
            for client in clients:
                try: client.close()
                except Exception as exc: summary.setdefault('bridge_cleanup_errors',[]).append(str(exc))
        finally:
            try:
                if changed:
                    assert config.read_bytes()==test_config_bytes, 'config changed externally during test: preserved; original backup available'
                    atomic_bytes(config,original)
                    summary['config_restored_exactly']=config.read_bytes()==original
            finally:
                if server:
                    server.shutdown(); server.server_close(); server_thread.join(3)
                    summary['server_thread_exited']=not server_thread.is_alive()
                summary['posts']=posts
                summary['bridge_exitcodes']=[c.process.returncode for c in clients]
                (out/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'evidence':str(out),'config_restored_exactly':summary['config_restored_exactly']}))


if __name__=='__main__': main()
