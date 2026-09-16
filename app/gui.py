"""Minimal HTML replay controller; all battle rendering remains native."""

import json, sys, traceback
from pathlib import Path
from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QTimer, QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSlider,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
)
from .runtime import Runtime
from .device import DATA, SETTINGS, settings
from .importer import convert


class Worker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(str)

    def __init__(self):
        super().__init__()
        self.runtime = Runtime(self.progress.emit)

    @Slot(str, object)
    def work(self, kind, payload):
        try:
            if kind == "convert":
                result = convert(*payload)
                self.runtime.discard_replay()
            elif kind == "load":
                result = self.runtime.load(payload)
            elif kind == "poll":
                result = self.runtime.status()
            elif kind == "seek":
                result = self.runtime.seek(payload)
            elif kind == "speed":
                result = self.runtime.set_speed(payload)
            else:
                result = getattr(self.runtime, kind)()
            self.finished.emit(kind, result)
        except Exception as e:
            cleanup_error = ""
            if kind == "load" and (
                self.runtime.offline
                or self.runtime.session is not None
                or self.runtime.script is not None
            ):
                try:
                    if self.runtime.offline:
                        self.runtime.online()
                    else:
                        self.runtime.abort_prepare()
                except Exception as cleanup:
                    cleanup_error = f"；自动恢复失败：{cleanup}"
            with (DATA / "errors.log").open("a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
            self.failed.emit(kind, str(e) + cleanup_error)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("连接设置")
        self.resize(650, 230)
        self.cfg = settings()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = {}
        for key, label in [
            ("adb", "ADB 程序"),
            ("serial", "设备地址"),
            ("port", "本地控制端口"),
        ]:
            v = self.cfg[key]
            edit = QLineEdit(
                json.dumps(v, ensure_ascii=False) if isinstance(v, list) else str(v)
            )
            self.fields[key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)
        layout.addWidget(
            QLabel("请先手动启动模拟器。支持原生 ARM64，或使用 libnb.so 的 Windows MuMu x86_64。")
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            c = {k: e.text().strip() for k, e in self.fields.items()}
            c["port"] = int(c["port"])
            if not 1024 <= c["port"] <= 65535:
                raise ValueError()
            SETTINGS.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
            self.accept()
        except Exception:
            QMessageBox.warning(self, "设置无效", "请检查 ADB 程序、设备地址和端口。")


class Window(QMainWindow):
    request = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Replay Studio")
        self.resize(680, 420)
        self.busy = False
        self.polling = False
        self.pending = None
        self.ready = False
        self.replay = None
        self.tick = 90
        self.paused = True
        self.closing = False
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.request.connect(self.worker.work)
        self.worker.finished.connect(self.done)
        self.worker.failed.connect(self.error)
        self.worker.progress.connect(self.message)
        self.thread.start()
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        row = QHBoxLayout()
        title = QLabel("Replay Studio")
        title.setStyleSheet("font-size:26px;font-weight:600")
        row.addWidget(title)
        row.addStretch()
        self.settings_btn = QPushButton("连接设置")
        self.settings_btn.clicked.connect(lambda: SettingsDialog(self).exec())
        row.addWidget(self.settings_btn)
        layout.addLayout(row)
        self.file_btn = QPushButton("导入 HTML")
        self.file_btn.clicked.connect(self.import_file)
        layout.addWidget(self.file_btn)
        self.summary = QLabel("尚未导入对局")
        self.summary.setWordWrap(True)
        self.summary.setMinimumHeight(56)
        layout.addWidget(self.summary)
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setRange(90, 6000)
        self.timeline.sliderReleased.connect(
            lambda: self.send("seek", self.timeline.value())
        )
        layout.addWidget(self.timeline)
        row = QHBoxLayout()
        self.time = QLabel("00:00")
        row.addWidget(self.time)
        row.addStretch()
        self.play_btn = QPushButton("准备回放")
        self.play_btn.setObjectName("primary")
        self.play_btn.clicked.connect(self.play_clicked)
        row.addWidget(self.play_btn)
        self.speed = QComboBox()
        self.speed.addItems(["0.25×", "0.5×", "1×", "2×", "4×", "8×", "16×"])
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(
            lambda i: self.send("speed", [0.25, 0.5, 1, 2, 4, 8, 16][i])
        )
        row.addWidget(self.speed)
        layout.addLayout(row)
        self.status_label = QLabel(
            "先启动模拟器，导入 HTML 后点击准备回放；届时会让游戏断网。"
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setStyleSheet(
            "QWidget{background:#f6f7f9;color:#182337;font-size:14px;} QPushButton,QComboBox,QLineEdit{background:white;border:1px solid #d8e0ea;border-radius:8px;padding:10px;} QPushButton#primary{background:#2563eb;color:white;} QPushButton:disabled{background:#edf0f4;color:#9da6b3;}"
        )
        self.controls()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(500)

    def message(self, text):
        self.status_label.setText(text)

    def controls(self):
        idle = not self.busy
        for w in (self.file_btn, self.settings_btn, self.speed):
            w.setEnabled(idle)
        self.play_btn.setEnabled(idle and self.replay is not None)
        self.timeline.setEnabled(idle and self.ready)
        self.timeline.setVisible(self.ready)
        self.speed.setVisible(self.ready)
        self.time.setVisible(self.ready)

    def send(self, kind, payload=None):
        if self.busy:
            return
        if self.polling:
            if kind != "poll":
                self.pending = (kind, payload)
            return
        if kind == "poll":
            self.polling = True
            self.request.emit(kind, payload)
            return
        self.busy = True
        self.controls()
        if kind != "poll":
            self.message("正在处理…")
        self.request.emit(kind, payload)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择对局 HTML", "", "HTML (*.html *.htm)"
        )
        if path:
            self.send("convert", (Path(path),))

    def play_clicked(self):
        if not self.ready:
            self.send("load", self.replay)
        else:
            self.send("play" if self.paused else "pause")

    def poll(self):
        if self.ready and not self.busy and not self.timeline.isSliderDown():
            self.send("poll")

    @Slot(str, object)
    def done(self, kind, result):
        if kind == "poll":
            self.polling = False
        else:
            self.busy = False
        if kind == "convert":
            self.replay = result
            self.ready = False
            self.play_btn.setText("准备回放")
            a, b = result["players"]
            self.summary.setText(
                a["name"]
                + "  vs  "
                + b["name"]
                + "\n"
                + str(len(result["events"]))
                + " 次动作 · HTML 已导入"
            )
            self.timeline.setMaximum(result["duration"])
            self.message("导入完成，点击准备回放。")
        elif kind == "online":
            self.ready = False
            self.play_btn.setText("准备回放")
            self.message("已恢复游戏联网")
        else:
            if kind == "load":
                self.ready = True
                self.timeline.setMaximum(result["cacheEnd"])
            if "tick" in result and self.ready:
                self.tick = max(90, int(result["tick"]))
                self.paused = bool(result.get("paused", True))
                if not self.timeline.isSliderDown():
                    self.timeline.setValue(self.tick)
                seconds = self.tick // 20
                self.time.setText(f"{seconds//60:02d}:{seconds%60:02d}")
                self.play_btn.setText("播放回放" if self.paused else "暂停")
                if kind != "poll":
                    self.message(
                        "已暂停" if self.paused else "正在模拟 · 画面显示在模拟器中"
                    )
                if result.get("finalized"):
                    self.paused = True
                    self.play_btn.setText("重新模拟")
                    self.message("对局已结束 · 可拖动时间轴回看")
        if kind != "poll":
            self.controls()
        if self.pending and not self.busy:
            pending = self.pending
            self.pending = None
            QTimer.singleShot(0, lambda: self.send(*pending))
        if self.closing:
            QTimer.singleShot(0, self.close)
        elif kind == "load":
            self.message(
                f'整场缓存就绪 · 预演算 {result["cacheSeconds"]:.1f} 秒 · 可直接拖动时间轴'
            )

    @Slot(str, str)
    def error(self, kind, text):
        self.busy = False
        self.polling = False
        self.message("未完成：" + text)
        if kind in ("online", "load", "poll", "seek"):
            self.ready = False
            self.play_btn.setText("准备回放")
        self.controls()
        if self.closing:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if self.busy or self.polling:
            self.closing = True
            self.pending = None
            self.timer.stop()
            self.worker.runtime.cancel.set()
            self.message("正在停止并清理缓存…")
            event.ignore()
            return
        if self.worker.runtime.offline:
            self.closing = True
            self.timer.stop()
            self.send("online")
            event.ignore()
            return
        self.timer.stop()
        self.thread.quit()
        self.thread.wait(2000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Replay Studio")
    lock = QLockFile(str(DATA / "studio.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(
            None, "Replay Studio", "程序已经运行，请切换到已打开的窗口。"
        )
        return
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.png"))))
    window = Window()
    window.show()
    sys.exit(app.exec())
