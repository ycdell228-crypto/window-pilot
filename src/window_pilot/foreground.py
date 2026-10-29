"""Explicit foreground input; never called as a background fallback."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from . import win32 as w
from .input_monitor import InputMonitor, MonitorError, exact_key

class Mouse(C.Structure):
    _fields_ = [('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
class Keyboard(C.Structure):
    _fields_ = [('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
class Hardware(C.Structure):
    _fields_ = [('msg',W.DWORD),('low',W.WORD),('high',W.WORD)]
class Payload(C.Union):
    _fields_ = [('mi',Mouse),('ki',Keyboard),('hi',Hardware)]
class Input(C.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type',W.DWORD),('data',Payload)]
class ThreadInfo(C.Structure):
    _fields_ = [('size',W.DWORD),('flags',W.DWORD),('active',W.HWND),('focus',W.HWND),('capture',W.HWND),('menu',W.HWND),('move',W.HWND),('caret',W.HWND),('rect',W.RECT)]
w.api(w.U,'SendInput',W.UINT,W.UINT,C.POINTER(Input),C.c_int)
w.api(w.U,'GetGUIThreadInfo',W.BOOL,W.DWORD,C.POINTER(ThreadInfo))
w.api(w.U,'GetAsyncKeyState',C.c_short,C.c_int)
w.api(w.U,'SetForegroundWindow',W.BOOL,W.HWND)
w.api(w.U,'WindowFromPoint',W.HWND,W.POINT)
w.api(w.U,'GetSystemMetrics',C.c_int,C.c_int)
KEYS = {'CTRL':0xa2,'SHIFT':0xa0,'ALT':0xa4,'ENTER':13,'TAB':9,'ESC':27,'BACKSPACE':8,'DELETE':46,
        'LEFT':37,'UP':38,'RIGHT':39,'DOWN':40,'HOME':36,'END':35,'PAGEUP':33,'PAGEDOWN':34,'SPACE':32}
KEYS.update({chr(i):i for i in range(65,91)})
KEYS.update({str(i):48+i for i in range(10)})
KEYS.update({'F'+str(i):111+i for i in range(1,13)})
MODIFIERS = {'CTRL','SHIFT','ALT'}
ACTION_BUDGET_SECONDS = 18.0

def validate(args, size):
    action=args['action']; extras=set(args)-{'target_id','frame_id','action'}
    required={'activate':set(),'click':{'x','y'},'keys':{'keys'},'text':{'text'},'drag':{'x','y','end_x','end_y','steps'}}
    if action not in required or extras != required[action]:
        raise w.PilotError('FOREGROUND_INVALID_PARAMETERS')
    if action in ('click','drag'):
        for x,y in [(args['x'],args['y'])]+([(args['end_x'],args['end_y'])] if action=='drag' else []):
            if type(x) is not int or type(y) is not int or not 0<=x<size[0] or not 0<=y<size[1]:
                raise w.PilotError('FOREGROUND_POINT_OUTSIDE_CLIENT')
    if action=='drag' and (type(args['steps']) is not int or not 2<=args['steps']<=20):
        raise w.PilotError('FOREGROUND_INVALID_STEPS')
    if action=='text':
        value=args['text']
        if not isinstance(value,str) or not 1<=len(value)<=512 or any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF for c in value):
            raise w.PilotError('FOREGROUND_INVALID_TEXT')
    if action=='keys':
        keys=args['keys']
        if (not isinstance(keys,list) or not 1<=len(keys)<=4 or len(set(keys))!=len(keys) or
            any(k not in KEYS for k in keys) or sum(k not in MODIFIERS for k in keys)!=1 or
            any(k in MODIFIERS for k in keys[-1:]) or any(k not in MODIFIERS for k in keys[:-1]) or
            ('ALT' in keys and keys[-1] in ('TAB','ESC','F4')) or ('CTRL' in keys and keys[-1]=='ESC') or ('CTRL' in keys and 'ALT' in keys)):
            raise w.PilotError('FOREGROUND_INVALID_KEYS')

def physical_clear(owned=()):
    owned=set(owned)
    for generic, sides in ((17,(162,163)),(16,(160,161)),(18,(164,165))):
        if owned.intersection(sides): owned.add(generic)  # ignore aggregate, still check the opposite side
    if any(w.U.GetAsyncKeyState(vk)&0x8000 for vk in range(1,255) if vk not in owned):
        raise w.PilotError('FOREGROUND_PHYSICAL_INPUT_HELD')

def native_focus(target,size, expected=None):
    w.bindable(target); w.verify(target)
    matching={'client_size_matches':w.geometry(target.hwnd)==tuple(size),
              'foreground_matches':w.U.GetForegroundWindow()==target.hwnd}
    if not all(matching.values()):
        exc=w.PilotError('FOREGROUND_TARGET_OR_GEOMETRY_CHANGED')
        exc.native_focus_diagnostic=matching
        raise exc
    if w.input_access(target)['blocked_by_integrity'] or w.process_scope(os.getpid())!=w.process_scope(target.pid):
        raise w.PilotError('FOREGROUND_SCOPE_DENIED')
    info=ThreadInfo(); info.size=C.sizeof(info)
    w.check(w.U.GetGUIThreadInfo(target.tid,C.byref(info)),'foreground_thread_info')
    if not info.focus or w.U.GetAncestor(info.focus,2)!=target.hwnd:
        raise w.PilotError('FOREGROUND_FOCUS_OUTSIDE_TARGET')
    pid=W.DWORD(); w.U.GetWindowThreadProcessId(info.focus,C.byref(pid))
    if pid.value!=target.pid or (expected is not None and info.focus!=expected):
        raise w.PilotError('FOREGROUND_FOCUS_CHANGED')
    return info.focus

PROBE_STAGES = {'startup','assemblies_load','dpi_init','request_wait','request_json','root_resolve',
                'providers_register','root_identity','point_resolve','focus_resolve','element_safety',
                'runtime_identity','ancestor_chain','response_write'}

class FocusProbeError(w.PilotError):
    pass

class FocusProbe:
    def __init__(self,target,deadline,monitor=None):
        self.deadline=deadline
        self.monitor=monitor
        self.target=target; self.lines=queue.Queue()
        self.diagnostic={'stage':'startup','source':'transport','apartment':'unknown'}
        self.worker_stage=dict(self.diagnostic)
        ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.process=subprocess.Popen([str(ps),'-NoProfile','-NonInteractive','-MTA','-ExecutionPolicy','Bypass','-File',str(Path(__file__).resolve().parents[2]/'scripts/uia-focus.ps1')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        def reader():
            for line in self.process.stdout:
                self.lines.put(line[:4096])
            self.lines.put(b'')
        threading.Thread(target=reader,daemon=True).start()
        def stages():
            for line in self.process.stderr:
                parts=line.decode('ascii','replace').split()
                if len(parts)==3 and parts[0]=='FOREGROUND_STAGE' and parts[1] in PROBE_STAGES and parts[2] in ('MTA','STA'):
                    self.worker_stage={'stage':parts[1],'source':'worker','apartment':parts[2]}
        threading.Thread(target=stages,daemon=True).start()
    def read(self,point=None):
        request={'hwnd':self.target.hwnd,'pid':self.target.pid,'mode':'point' if point else 'focus'}
        if point: request.update(x=point.x,y=point.y)
        phase='request_write'
        try:
            if self.monitor is not None: self.monitor.check()
            self.process.stdin.write((json.dumps(request)+'\n').encode('ascii')); self.process.stdin.flush()
            remaining=min(6,self.deadline-time.monotonic())
            if remaining<=0:
                phase='deadline'; raise ValueError()
            phase='response_wait'
            until=time.monotonic()+remaining
            while True:
                if self.monitor is not None: self.monitor.check()
                remaining=until-time.monotonic()
                if remaining<=0: raise queue.Empty()
                try:
                    line=self.lines.get(timeout=min(0.02,remaining))
                    break
                except queue.Empty:
                    continue
            phase='response_eof' if not line else 'response_json'
            value=json.loads(line)
            if (value.get('stage') not in PROBE_STAGES or value.get('apartment') not in ('MTA','STA')):
                raise ValueError()
            self.diagnostic={'stage':value['stage'],'source':'worker','apartment':value['apartment']}
            phase='worker_rejected'
            if value.get('ok') is not True or value['apartment']!='MTA' or not isinstance(value.get('fingerprint'),str): raise ValueError()
            return value['fingerprint']
        except MonitorError:
            raise
        except Exception:
            if phase!='worker_rejected': self.diagnostic=dict(self.worker_stage)
            stage=self.diagnostic['stage']
            raise FocusProbeError('FOREGROUND_PROTECTED_OR_UNVERIFIED_FOCUS: '+phase+'/'+stage) from None
    def close(self):
        self.process.kill(); self.process.wait(timeout=2)
        self.process.stdin.close(); self.process.stdout.close(); self.process.stderr.close()

def keyboard(vk=0,scan=0,flags=0):
    vk=exact_key(vk,scan,bool(flags & 1))
    event=Input(); event.type=1; event.ki=Keyboard(vk,scan,flags | (1 if vk in (33,34,35,36,37,38,39,40,45,46,163,165) else 0),0,0); return event

def mouse(flags,point=None):
    event=Input(); event.type=0
    if point:
        left,top,width,height=[w.U.GetSystemMetrics(i) for i in (76,77,78,79)]
        if width<2 or height<2 or not left<=point.x<left+width or not top<=point.y<top+height:
            raise w.PilotError('FOREGROUND_POINT_OUTSIDE_DESKTOP')
        event.mi=Mouse(round((point.x-left)*65535/(width-1)),round((point.y-top)*65535/(height-1)),0,flags|0x8000|0x4000,0,0)
    else: event.mi=Mouse(0,0,0,flags,0,0)
    return event

def inject(event):
    if w.U.SendInput(1,C.byref(event),C.sizeof(Input))!=1:
        raise w.PilotError('FOREGROUND_INJECTION_PARTIAL_OR_DENIED')

def act(target,size,args,before_input):
    validate(args,size)
    physical_clear()
    w.bindable(target); w.verify(target)
    if w.input_access(target)['blocked_by_integrity'] or w.process_scope(os.getpid())!=w.process_scope(target.pid):
        raise w.PilotError('FOREGROUND_SCOPE_DENIED')
    if tuple(size)!=w.geometry(target.hwnd): raise w.PilotError('FOREGROUND_GEOMETRY_CHANGED')
    origin=W.POINT(); w.check(w.U.ClientToScreen(target.hwnd,C.byref(origin)),'foreground_origin')
    def point(x,y):
        value=W.POINT(origin.x+x,origin.y+y)
        if w.U.GetAncestor(w.U.WindowFromPoint(value),2)!=target.hwnd:
            raise w.PilotError('FOREGROUND_POINT_OCCLUDED')
        return value
    deadline=time.monotonic()+ACTION_BUDGET_SECONDS
    activation=None; native_diagnostic=None
    probe=None; monitor=None; held={}; cursor_expected=None; started=False; attempted=False; sent=0; release_failed=False; cleanup_failed=False; deferred=0; error=None
    def emit(event,down=None,up=None):
        nonlocal attempted
        monitor.check()
        monitor.tag(event)
        if down is not None: held[down]=up
        attempted=True
        inject(event)
    def release_owned(key,event):
        nonlocal deferred
        if not monitor.may_release(key):
            deferred+=1  # external same-key down owns this state now; never release it
            return False
        monitor.tag(event)
        inject(event)
        return True
    try:
        monitor=InputMonitor()
        physical_clear()  # close held-input gap while the pass-through hooks were installing
        monitor.check()
        if args['action']=='activate':
            monitor.check()
            before_input(); started=True
            monitor.check(); attempted=True
            accepted=bool(w.U.SetForegroundWindow(target.hwnd))
            time.sleep(0.05)
            activation={'set_foreground_returned':accepted,
                        'foreground_is_target':w.U.GetForegroundWindow()==target.hwnd,
                        'client_size_matches':w.geometry(target.hwnd)==tuple(size)}
            if not activation['client_size_matches']:
                raise w.PilotError('FOREGROUND_GEOMETRY_CHANGED')
            if not activation['foreground_is_target']:
                raise w.PilotError('FOREGROUND_ACTIVATION_NOT_GRANTED')
            w.verify(target)
        elif args['action']=='click':
            # Explicit real click may activate the observed target naturally. No keyboard
            # is injected until later calls have verified actual target-owned focus.
            probe=FocusProbe(target,deadline,monitor)
            destination=point(args['x'],args['y'])
            def pointer_check():
                monitor.check()
                if time.monotonic()>deadline: raise w.PilotError('FOREGROUND_ACTION_DEADLINE')
                w.bindable(target); w.verify(target)
                if w.input_access(target)['blocked_by_integrity'] or w.process_scope(os.getpid())!=w.process_scope(target.pid):
                    raise w.PilotError('FOREGROUND_SCOPE_DENIED')
                current=W.POINT(); w.check(w.U.ClientToScreen(target.hwnd,C.byref(current)),'foreground_origin')
                if tuple(size)!=w.geometry(target.hwnd) or (current.x,current.y)!=(origin.x,origin.y):
                    raise w.PilotError('FOREGROUND_GEOMETRY_CHANGED')
                point(args['x'],args['y']); physical_clear(held)
            pointer_check(); probe.read(destination); pointer_check()
            before_input(); started=True
            emit(mouse(1,destination)); sent+=1; time.sleep(0.02)
            pointer_check(); probe.read(destination); pointer_check()
            cursor=W.POINT(); w.check(w.U.GetCursorPos(C.byref(cursor)),'foreground_cursor')
            if abs(cursor.x-destination.x)>1 or abs(cursor.y-destination.y)>1:
                raise w.PilotError('FOREGROUND_CURSOR_CHANGED')
            emit(mouse(2),1,mouse(4)); sent+=1
            time.sleep(0.02)
            native_focus(target,size); probe.read()
            sent+=int(release_owned(1,mouse(4))); held.pop(1,None)
            native_focus(target,size); probe.read()
        else:
            focus=native_focus(target,size)
            probe=FocusProbe(target,deadline,monitor)
            fingerprint=probe.read()
            def check():
                monitor.check()
                if time.monotonic()>deadline: raise w.PilotError('FOREGROUND_ACTION_DEADLINE')
                current=W.POINT(); w.check(w.U.ClientToScreen(target.hwnd,C.byref(current)),'foreground_origin')
                if (current.x,current.y)!=(origin.x,origin.y): raise w.PilotError('FOREGROUND_GEOMETRY_CHANGED')
                physical_clear(held)
                native_focus(target,size,focus)
                if probe.read()!=fingerprint:
                    raise w.PilotError('FOREGROUND_FOCUS_CHANGED')
                native_focus(target,size,focus)
                if time.monotonic()>deadline: raise w.PilotError('FOREGROUND_ACTION_DEADLINE')
                if cursor_expected is not None:
                    cursor=W.POINT(); w.check(w.U.GetCursorPos(C.byref(cursor)),'foreground_cursor')
                    if abs(cursor.x-cursor_expected.x)>1 or abs(cursor.y-cursor_expected.y)>1:
                        raise w.PilotError('FOREGROUND_CURSOR_CHANGED')
            if args['action'] in ('click','drag'):
                probe.read(point(args['x'],args['y']))
            check(); before_input(); started=True
            def send(event,down=None,up=None):
                nonlocal sent
                check()
                if down == 1:
                    probe.read(cursor_expected)
                    check()
                emit(event,down,up); sent+=1
                if down is None and up is not None: held.pop(up,None)
            action=args['action']
            if action=='text':
                units=args['text'].encode('utf-16-le')
                for offset in range(0,len(units),2):
                    scan=int.from_bytes(units[offset:offset+2],'little')
                    # Virtual-key 0 is only an internal owned Unicode marker.
                    send(keyboard(scan=scan,flags=4),0,keyboard(scan=scan,flags=6))
                    sent+=int(release_owned(0,keyboard(scan=scan,flags=6))); held.pop(0,None)
            elif action=='keys':
                for name in args['keys']:
                    vk=KEYS[name]; send(keyboard(vk),vk,keyboard(vk,flags=2))
                for name in reversed(args['keys']):
                    vk=KEYS[name]; sent+=int(release_owned(vk,keyboard(vk,flags=2))); held.pop(vk,None)
            else:
                start=point(args['x'],args['y'])
                send(mouse(1,start))
                cursor_expected=start
                time.sleep(0.01)
                # Click can intentionally change focus; require target + safety probe after it.
                send(mouse(2),1,mouse(4))
                # This explicitly requested point action may move focus within the target.
                focus=native_focus(target,size); fingerprint=probe.read()
                if action=='drag':
                    for index in range(1,args['steps']+1):
                        x=round(args['x']+(args['end_x']-args['x'])*index/args['steps'])
                        y=round(args['y']+(args['end_y']-args['y'])*index/args['steps'])
                        destination=point(x,y)
                        send(mouse(1,destination)); cursor_expected=destination; time.sleep(0.02)
                sent+=int(release_owned(1,mouse(4))); held.pop(1,None)
                focus=native_focus(target,size); fingerprint=probe.read()
            check()
    except Exception as exc:
        native_diagnostic=getattr(exc,'native_focus_diagnostic',None)
        allowed={'FOREGROUND_PHYSICAL_INPUT_HELD','FOREGROUND_TARGET_OR_GEOMETRY_CHANGED','FOREGROUND_FOCUS_OUTSIDE_TARGET','FOREGROUND_FOCUS_CHANGED','FOREGROUND_PROTECTED_OR_UNVERIFIED_FOCUS','FOREGROUND_POINT_OCCLUDED','FOREGROUND_INJECTION_PARTIAL_OR_DENIED','FOREGROUND_ACTION_DEADLINE','FOREGROUND_GEOMETRY_CHANGED','FOREGROUND_CURSOR_CHANGED','FOREGROUND_ACTIVATION_NOT_GRANTED'}
        error=str(exc) if isinstance(exc,(FocusProbeError,MonitorError)) or (isinstance(exc,w.PilotError) and str(exc) in allowed) else ('FOREGROUND_INPUT_INTERRUPTED' if started else 'FOREGROUND_SAFETY_CHECK_REJECTED')
    finally:
        for key,release in reversed(list(held.items())):
            try:
                if attempted: release_owned(key,release)
            except Exception: release_failed=True
        if probe is not None:
            try: probe.close()
            except Exception:
                cleanup_failed=True
                error=error or 'FOREGROUND_PROBE_CLEANUP_FAILED'
        if monitor is not None:
            try: monitor.close()
            except MonitorError as exc:
                cleanup_failed=True
                error=error or str(exc)
            if monitor.failed: error=error or 'FOREGROUND_INPUT_MONITOR_UNAVAILABLE'
    if not started:
        exc=w.PilotError(error or 'FOREGROUND_SAFETY_CHECK_REJECTED')
        if monitor is not None:
            exc.input_monitor_counts=dict(monitor.counts)
            exc.external_input_detected=any(value for key,value in monitor.counts.items() if key.startswith('external_'))
        exc.native_focus_diagnostic=native_diagnostic
        raise exc
    return {'status':('unknown' if error or release_failed or cleanup_failed or deferred else 'injected') if attempted else 'not_sent',
            'input_sent':bool(sent) or (attempted and args['action']=='activate'),
            'delivery':'not_sent' if not attempted else 'sent_effect_unverified' if sent or args['action']=='activate' else 'attempted_outcome_unknown',
            'input_attempted':attempted,'event_count':sent,
            'effect':'unverified' if attempted else 'not_sent','error':error,'owned_input_release_failed':release_failed,
            'input_cleanup_failed':cleanup_failed,'input_monitor_failed':monitor.failed if monitor is not None else False,
            'activation_diagnostic':activation,
            'native_focus_diagnostic':native_diagnostic,
            'external_input_detected':any(value for key,value in monitor.counts.items() if key.startswith('external_')) if monitor is not None else False,
            'input_monitor_counts':dict(monitor.counts) if monitor is not None else None,
            'release_deferred_count':deferred,
            'focus_diagnostic':dict(probe.diagnostic) if probe is not None else None,
            'next':'observe actual effect; unknown results require explicit review, never replay'}
