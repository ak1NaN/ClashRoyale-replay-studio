import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock
from test_ability_import import ROOT
from PySide6.QtCore import QObject,QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from native_engine.desktop.gui import Window

class Changes(QObject):
    def __init__(self):super().__init__();self.enabled=0
    def eventFilter(self,obj,event):
        if event.type()==QEvent.EnabledChange:self.enabled+=1
        return False

class PollingTests(unittest.TestCase):
    def test_poll_keeps_controls_enabled_and_does_not_seek(self):
        app=QApplication.instance() or QApplication([])
        window=Window();window.timer.stop();window.ready=True;window.replay={};window.controls()
        window.worker.runtime.status=Mock(return_value={'tick':110,'paused':True})
        window.worker.runtime.seek=Mock()
        changes=Changes()
        for widget in (window.play_btn,window.speed,window.timeline):widget.installEventFilter(changes)
        window.send('poll')
        self.assertTrue(window.play_btn.isEnabled())
        for _ in range(30):
            app.processEvents();QTest.qWait(10)
            if not window.polling:break
        self.assertFalse(window.polling)
        self.assertEqual(changes.enabled,0)
        self.assertEqual(window.timeline.value(),110)
        window.worker.runtime.seek.assert_not_called()
        window.close();app.processEvents()

    def test_connection_error_allows_preparing_imported_replay(self):
        app=QApplication.instance() or QApplication([])
        window=Window();window.timer.stop();window.ready=True
        window.replay={}
        window.error('poll','connection closed')
        self.assertFalse(window.ready)
        self.assertTrue(window.play_btn.isEnabled())
        self.assertIn('8×',[window.speed.itemText(i) for i in range(window.speed.count())])
        self.assertIn('16×',[window.speed.itemText(i) for i in range(window.speed.count())])
        window.close();app.processEvents()

    def test_import_does_not_disconnect_until_prepare(self):
        app=QApplication.instance() or QApplication([])
        window=Window();window.timer.stop();window.send=Mock()
        replay={'players':[{'name':'A'},{'name':'B'}],'events':[],'duration':500}
        window.done('convert',replay);app.processEvents()
        window.send.assert_not_called()
        self.assertFalse(window.worker.runtime.offline)
        self.assertFalse(hasattr(window,'mode'))
        self.assertTrue(window.play_btn.isEnabled())
        window.play_clicked();window.send.assert_called_once_with('load',replay)
        window.close();app.processEvents()
