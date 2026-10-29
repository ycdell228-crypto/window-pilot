"""Foreground effects on project-owned fixtures. No user software or installed IPC."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
if sys.platform=='win32':
    from window_pilot import win32 as w, foreground as fg
    from window_pilot.service import Service
    from window_pilot.coordination import Coordinator
    from window_pilot.admin_service import create_connection_service

@unittest.skipUnless(sys.platform=='win32','requires Windows')
class ForegroundNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get('CI') and os.environ.get('WINDOW_PILOT_NATIVE_TESTS')!='1') or not w.U.GetForegroundWindow():
            raise unittest.SkipTest('requires interactive local desktop; native tests disabled in CI')
        cls.evidence=[]
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.config=self.root/'config.json';self.config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        self.owner=Service(self.config)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.owner.dispose)
        self.hwnd=self.owner.call('launch_test',{'kind':'foreground'})['windows'][0]['hwnd']
        self.coordinator=Coordinator()
        self.a=create_connection_service(self.config,self.root/'a.lock','a',self.coordinator)
        self.addCleanup(self.a.dispose)
        self.b=create_connection_service(self.config,self.root/'b.lock','b',self.coordinator)
        self.addCleanup(self.b.dispose)
        self.token=self.bind(self.a,'observe_and_foreground')
        self.a.call('window_control',dict(target_id=self.token,operation='acquire'))
        self.focus_edit()
        activated=self.action('activate')
        self.assertEqual(activated['status'],'injected',activated)
    @classmethod
    def tearDownClass(cls):
        dest=os.environ.get('WINDOW_PILOT_EVIDENCE_DIR')
        if dest:
            path=Path(dest).resolve()
            if not path.is_relative_to(Path(__file__).resolve().parents[1]/'.local'): raise AssertionError('private evidence only')
            path.mkdir(parents=True,exist_ok=True)
            (path/'foreground-effects.json').write_text(json.dumps(cls.evidence,ensure_ascii=False,indent=2),encoding='utf8')
    def bind(self,service,access,hwnd=None):
        service.call('list_windows',{})
        return service.call('bind_window',dict(hwnd=hwnd or self.hwnd,access=access,purpose='project-owned foreground acceptance'))['target_id']
    def frame(self): return self.a.call('observe',dict(target_id=self.token))
    def action(self,action,**parameters):
        frame=self.frame()
        result=self.a.call('foreground_action',dict(target_id=self.token,frame_id=frame['frame_id'],action=action,**parameters))
        self.frame()
        return result
    def tree(self):
        value=self.a.call('observe_controls',dict(target_id=self.token,max_nodes=128,max_depth=8))
        self.assertEqual(value['status'],'ok',value)
        return value
    def node(self,identifier):
        return next(n for n in self.tree()['nodes'] if n['automation_id']==identifier)
    def point(self,identifier):
        b=self.node(identifier)['bounds_client'];return dict(x=round(b['x']+b['width']/2),y=round(b['y']+b['height']/2))
    def focus_edit(self):
        result=self.action('click',**self.point('foreground-value'))
        self.assertEqual(result['status'],'injected',result)
    def save_effect_image(self,name):
        destination=os.environ.get('WINDOW_PILOT_EVIDENCE_DIR')
        if not destination:return
        path=Path(destination).resolve()
        if not path.is_relative_to(Path(__file__).resolve().parents[1]/'.local'):raise AssertionError('private evidence only')
        path.mkdir(parents=True,exist_ok=True)
        frame=self.frame()
        (path/name).write_bytes((self.a.local/'frames'/(frame['frame_id']+'.png')).read_bytes())
    def test_unicode_and_shortcut_have_real_effects(self):
        self.focus_edit()
        self.assertEqual(self.action('keys',keys=['CTRL','A'])['status'],'injected')
        sample='中文验收 Ω 😀'
        result=self.action('text',text=sample)
        self.assertEqual(result['status'],'injected',result)
        self.assertEqual(self.node('foreground-echo')['name'],'Echo: '+sample)
        self.save_effect_image('unicode-after.png')
        self.assertEqual(self.action('keys',keys=['CTRL','A'])['status'],'injected')
        self.assertEqual(self.action('keys',keys=['BACKSPACE'])['status'],'injected')
        self.assertEqual(self.node('foreground-echo')['name'],'Echo: ')
        audit=(self.a.local/'audit.jsonl').read_text(encoding='utf8')
        self.assertNotIn(sample,audit);self.assertNotIn('"CTRL"',audit);self.assertNotIn('"BACKSPACE"',audit)
        self.evidence.append(dict(test=self.id(),unicode_exact_echo=True,ctrl_a_backspace_cleared=True,audit_text_and_keys_redacted=True))
    def test_drag_changes_actual_thumb_position(self):
        start=self.point('drag-thumb')
        result=self.action('drag',**start,end_x=start['x']+120,end_y=start['y'],steps=6)
        self.assertEqual(result['status'],'injected',result)
        after=self.node('drag-thumb')['bounds_client']
        status=self.node('drag-echo')['name']
        self.assertAlmostEqual(after['x'],start['x']-20+120,delta=3)
        self.assertEqual(status,'Drag x: 160')
        self.save_effect_image('drag-after.png')
        self.assertFalse(w.U.GetAsyncKeyState(1)&0x8000)
        self.evidence.append(dict(test=self.id(),drag_status=status,actual_thumb_x=after['x'],button_released=True))
    def test_scope_old_frame_and_password_refusals(self):
        for access in ('observe','observe_and_click','observe_and_mouse','observe_and_control'):
            token=self.bind(self.b,access)
            frame=self.b.call('observe',dict(target_id=token))
            with self.assertRaisesRegex(w.PilotError,'FOREGROUND_SCOPE_REQUIRED'):
                self.b.call('foreground_action',dict(target_id=token,frame_id=frame['frame_id'],action='keys',keys=['ENTER']))
        self.focus_edit()
        old=self.frame()
        self.assertEqual(self.action('keys',keys=['CTRL','A'])['status'],'injected')
        with self.assertRaisesRegex(w.PilotError,'STALE_FRAME|INVALIDATED'):
            self.a.call('foreground_action',dict(target_id=self.token,frame_id=old['frame_id'],action='text',text='do not send'))
        # Point probe refuses a password field before mouse movement/down.
        password=self.point('foreground-password'); before=w.desktop_state()
        with self.assertRaisesRegex(w.PilotError,'PROTECTED_OR_UNVERIFIED'):
            self.action('click',**password)
        self.assertEqual(w.desktop_state()['cursor'],before['cursor'])
        # Password focus reached by an explicit fixture-only Tab must still refuse text.
        fg.inject(fg.keyboard(9)); fg.inject(fg.keyboard(9,flags=2))
        import time; time.sleep(0.05)
        with self.assertRaisesRegex(w.PilotError,'PROTECTED_OR_UNVERIFIED'):
            self.action('text',text='synthetic secret never delivered')
        self.evidence.append(dict(test=self.id(),old_scopes_refused=4,old_frame_refused=True,password_point_and_text_refused=True))
    def test_partial_key_injection_releases_and_fault_survives_connection(self):
        self.focus_edit(); real=fg.inject; count=0
        def fail_second(event):
            nonlocal count
            count+=1
            if count==2: raise w.PilotError('controlled second injection failure')
            return real(event)
        with patch.object(fg,'inject',side_effect=fail_second):
            result=self.action('keys',keys=['CTRL','A'])
        self.assertEqual(result['status'],'unknown',result)
        self.assertFalse(result['owned_input_release_failed'])
        for vk in (17,162,163): self.assertFalse(w.U.GetAsyncKeyState(vk)&0x8000)
        self.a.dispose()
        token=self.bind(self.b,'observe_and_foreground')
        self.assertTrue(self.b.call('window_control',dict(target_id=token,operation='acquire'))['faulted'])
        frame=self.b.call('observe',dict(target_id=token))
        with self.assertRaisesRegex(w.PilotError,'WINDOW_INPUT_FAULTED'):
            self.b.call('foreground_action',dict(target_id=token,frame_id=frame['frame_id'],action='keys',keys=['ENTER']))
        self.evidence.append(dict(test=self.id(),controlled_partial_injection=True,ctrl_released=True,shared_fault_retained=True))
    def test_drag_focus_loss_releases_button_and_stops(self):
        self.assertEqual(self.action('click',**self.point('arm-focus-loss'))['status'],'injected')
        start=self.point('drag-thumb')
        result=self.action('drag',**start,end_x=start['x']+120,end_y=start['y'],steps=10)
        self.assertEqual(result['status'],'unknown',result)
        self.assertIn('PROTECTED_OR_UNVERIFIED_FOCUS',result['error'])
        self.assertTrue(self.node('foreground-password')['state']['has_keyboard_focus'])
        self.assertEqual(w.U.GetForegroundWindow(),self.hwnd)
        self.assertFalse(w.U.GetAsyncKeyState(1)&0x8000)
        self.assertFalse(result['owned_input_release_failed'])
        self.evidence.append(dict(test=self.id(),fixture_triggered_real_password_focus=True,
                                 actual_uia_password_focused=True,event_count=result['event_count'],button_released=True))
    def test_preexisting_key_refused_without_releasing_it(self):
        self.focus_edit()
        # Controlled existing synthetic key state, then genuine OS state checks.
        fg.inject(fg.keyboard(17))
        try:
            with self.assertRaisesRegex(w.PilotError,'PHYSICAL_INPUT_HELD'):
                self.action('text',text='must not arrive')
            self.assertTrue(w.U.GetAsyncKeyState(17)&0x8000)
            self.assertEqual(self.node('foreground-echo')['name'],'Echo: initial')
        finally:
            fg.inject(fg.keyboard(17,flags=2))
        self.assertFalse(w.U.GetAsyncKeyState(17)&0x8000)
        self.evidence.append(dict(test=self.id(),controlled_preexisting_key_state=True,
                                 refused=True,existing_key_not_released_by_action=True,test_cleanup_released=True))
    def test_remaining_budget_stops_and_releases_after_real_ctrl_down(self):
        import time
        self.focus_edit(); real=fg.FocusProbe.read; delayed=False
        def stall(probe,point=None):
            nonlocal delayed
            if w.U.GetAsyncKeyState(17)&0x8000 and not delayed:
                delayed=True
                time.sleep(max(0,probe.deadline-time.monotonic())+0.03)
            return real(probe,point)
        start=time.monotonic()
        # Shortened real-time budget. No fake monotonic clock or simulated OS success.
        with patch.object(fg,'ACTION_BUDGET_SECONDS',5.0), patch.object(fg.FocusProbe,'read',stall):
            result=self.action('keys',keys=['CTRL','A'])
        elapsed=time.monotonic()-start
        self.assertTrue(delayed)
        self.assertEqual(result['status'],'unknown',result)
        self.assertIn('deadline',result['error'])
        self.assertGreaterEqual(elapsed,5.0);self.assertLess(elapsed,8.0)
        self.assertFalse(w.U.GetAsyncKeyState(17)&0x8000)
        self.assertFalse(result['owned_input_release_failed'])
        self.assertEqual(self.node('foreground-echo')['name'],'Echo: initial')
        self.evidence.append(dict(test=self.id(),controlled_real_delay=True,test_budget_seconds=5,
                                 production_budget_seconds=18,elapsed_ms=round(elapsed*1000),ctrl_released=True))
    def test_desktop_gate_excludes_competing_input_across_windows(self):
        # Second genuine native window. Existing production factory remains in use.
        config2=self.root/'other.json'; config2.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        other=Service(config2,lock_path=self.root/'other-owner.lock');self.addCleanup(other.dispose)
        hwnd=other.call('launch_test',{})['windows'][0]['hwnd']
        token=self.bind(self.b,'observe_and_click',hwnd)
        self.b.call('window_control',dict(target_id=token,operation='acquire'))
        frame=self.b.call('observe',dict(target_id=token))
        frame_a=self.frame(); target=self.a.targets[self.token]
        # Controlled pause after entering the production command gate, before native input.
        with self.coordinator.command('a',target,foreground=True):
            with self.assertRaisesRegex(w.PilotError,'DESKTOP_INPUT_BUSY'):
                self.b.call('click',dict(target_id=token,frame_id=frame['frame_id'],x=40,y=40))
        with self.coordinator.command('b',self.b.targets[token]):
            with self.assertRaisesRegex(w.PilotError,'DESKTOP_INPUT_BUSY'):
                self.a.call('foreground_action',dict(target_id=self.token,frame_id=frame_a['frame_id'],action='activate'))
        self.b.call('click',dict(target_id=token,frame_id=frame['frame_id'],x=40,y=40))
        self.assertIn('clicks=1',w.text(hwnd))
        self.b.call('observe',dict(target_id=token))
        self.evidence.append(dict(test=self.id(),other_window_input_refused_during_foreground=True,background_works_after=True))
