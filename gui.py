#!/usr/bin/env python3
"""League skin fantome builder — PySide6 桌面界面（含共享构建逻辑）.

双击运行本文件即可启动。
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QEvent, QPoint, QPointF, QSize
from PySide6.QtGui import QFont, QPainter, QPixmap, QPainterPath, QColor, QIcon, QPen
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QFileDialog, QFrame, QMessageBox,
)

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "pref" / "gui_config.json"
DEFAULT_OUT = HERE / "out"

_lock = threading.Lock()
state = {"running": False, "log": "", "started_at": 0.0, "exit_code": None}
proc: subprocess.Popen | None = None


# ---------------------------------------------------------------- 共享构建逻辑

def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def check_league(league: str) -> dict:
    """校验英雄联盟安装目录，返回 {ok, msg}。"""
    league = (league or "").strip()
    if not league or not Path(league).exists():
        return {"ok": False, "msg": "目录不存在"}
    cd = Path(league) / "Game" / "DATA" / "FINAL" / "Champions"
    if not cd.exists():
        return {"ok": False,
                "msg": "未找到 Game\\DATA\\FINAL\\Champions，请选择英雄联盟安装根目录（包含 Game 文件夹）"}
    nwads = len(list(cd.glob("*.wad.client")))
    return {"ok": True, "msg": f"检测到 {nwads} 个英雄 WAD 文件"}


def log_append(text: str):
    with _lock:
        state["log"] += text
        if len(state["log"]) > 200_000:      # ponytail: 日志上限 200KB，超出丢最旧部分
            state["log"] = state["log"][-200_000:]


def _python_exe() -> str:
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("pythonw.exe"):
        alt = exe[:-5] + ".exe"              # pythonw -> python，保证子进程 stdout 正常
        if os.path.exists(alt):
            return alt
    return exe


def start_build(cfg: dict) -> tuple[bool, str]:
    global proc
    with _lock:
        if state["running"]:
            return False, "已有构建正在进行中"
        league = (cfg.get("league") or "").strip()
        out = (cfg.get("out") or "").strip() or str(DEFAULT_OUT)
        if not league or not Path(league).exists():
            return False, f"游戏安装目录不存在:\n{league}"
        state.update(log="", running=True, started_at=time.time(), exit_code=None)

    # 注意：锁外才能调用 log_append / subprocess（threading.Lock 不可重入，
    # 持锁期间再进 log_append 会死锁，导致界面卡死）
    cmd = [_python_exe(), str(HERE / "build.py"), "--league", league, "--out", out]
    cmd.append("--chromas" if cfg.get("chromas", True) else "--no-chromas")
    if cfg.get("refresh"):
        cmd.append("--refresh-hashes")
    only = [k.strip() for k in str(cfg.get("only", "")).split(",") if k.strip()]
    if only:
        cmd += ["--only", ",".join(only)]
    if str(cfg.get("limit", "")).strip():
        cmd += ["--limit", str(cfg["limit"]).strip()]
    if str(cfg.get("workers", "")).strip():
        cmd += ["--workers", str(cfg["workers"]).strip()]

    save_config(cfg)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"       # 子进程输出实时刷新，否则日志被缓冲、界面一直空白
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", env=env, creationflags=creationflags,
            cwd=str(HERE),
        )
    except OSError as e:
        with _lock:
            state["running"] = False
        return False, f"启动构建失败:\n{e}"

    log_append("$ " + " ".join(cmd) + "\n")
    threading.Thread(target=_watch, daemon=True).start()
    return True, ""


def _watch():
    global proc
    p = proc
    for line in p.stdout:
        log_append(line)
    rc = p.wait()
    with _lock:
        state["running"] = False
        state["exit_code"] = rc
    log_append(f"\n[进程退出, 退出码 {rc}]")
    log_append(f"[总用时 {time.time() - state['started_at']:.1f} 秒]\n")


def stop_build():
    p = proc
    if p and p.poll() is None:
        log_append("\n[已请求停止...]\n")
        if os.name == "nt":
            subprocess.Popen(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            p.terminate()


# ---------------------------------------------------------------- 样式表

APP_QSS = """
* { outline: none; }
QWidget#Root {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #111827, stop:0.55 #0e1420, stop:1 #0a0d16);
  border: 1px solid #26304a;
}
QFrame#Card {
  background: rgba(255, 255, 255, 0.028);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
}
QFrame#Card:hover { border-color: rgba(200, 170, 110, 0.25); }
QLabel#CardTitle { color: #f0e6d2; font-size: 13.5px; font-weight: 600; letter-spacing: 1px; }
QLabel#FieldLabel { color: #9aa3b5; font-size: 12px; }
QLabel#FieldLabel[accent="true"] { color: #c8aa6e; }
QLabel#Hint { color: #5b6475; font-size: 11.5px; }
QLabel#Hint[ok="true"] { color: #3fb950; }
QLabel#Hint[err="true"] { color: #f85149; }

QLineEdit {
  background: #0c111d;
  border: 1px solid #28324d;
  border-radius: 7px;
  padding: 8px 11px;
  color: #e6e9f0;
  font-size: 13px;
  selection-background-color: #c8aa6e;
  selection-color: #141a12;
  placeholder-text-color: #4b5468;
}
QLineEdit:focus { border-color: #c8aa6e; }

QPushButton#Ghost {
  background: #1b2334;
  border: 1px solid #2e3952;
  border-radius: 7px;
  padding: 8px 14px;
  color: #c3c9d6;
  font-size: 12.5px;
}
QPushButton#Ghost:hover { background: #242e44; border-color: #c8aa6e; }
QPushButton#Ghost:pressed { background: #2a3550; }
QPushButton#Ghost:disabled { color: #5b6475; background: #141a28; border-color: #232c42; }

QPushButton#Primary {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f0e6d2, stop:0.55 #c8aa6e, stop:1 #a8823d);
  color: #141a12;
  font-size: 15px; font-weight: 700; letter-spacing: 3px;
  border: none; border-radius: 10px;
  padding: 13px 30px;
}
QPushButton#Primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fdf6e9, stop:0.55 #d4b97f, stop:1 #b8913f); }
QPushButton#Primary:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e0d2b4, stop:0.55 #b8913f, stop:1 #96702c); }
QPushButton#Primary:disabled { background: #2a3550; color: #7c8798; }

QPushButton#Danger {
  background: #2a1520;
  border: 1px solid #e84057;
  border-radius: 10px;
  color: #ff8598;
  font-size: 14px; font-weight: 600; letter-spacing: 1px;
  padding: 12px 22px;
}
QPushButton#Danger:hover { background: #3a1a28; }
QPushButton#Danger:disabled { background: #141a28; border-color: #4a2a36; color: #7c8798; }

QPushButton#WinBtn, QPushButton#CloseBtn {
  background: transparent;
  border: none; border-radius: 0px;
  min-width: 36px; min-height: 28px; padding: 0;
}
QPushButton#WinBtn:hover { background: rgba(200, 170, 110, 0.18); }
QPushButton#CloseBtn:hover { background: #e2443c; }

QPlainTextEdit#Log {
  background: #0a0e17;
  border: 1px solid #1f2942;
  border-radius: 10px;
  padding: 10px;
  color: #b8c4dc;
  font-family: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
  font-size: 12px;
  selection-background-color: #2c3a5c;
}
QPlainTextEdit#Log QScrollBar:vertical, QPlainTextEdit#Log QScrollBar:horizontal {
  background: #0c111d; width: 10px; height: 10px; margin: 0;
}
QPlainTextEdit#Log QScrollBar::handle:vertical, QPlainTextEdit#Log QScrollBar::handle:horizontal {
  background: #2a3450; border-radius: 5px; min-height: 24px;
}
QPlainTextEdit#Log QScrollBar::handle:hover { background: #39476b; }
QPlainTextEdit#Log QScrollBar::add-line, QPlainTextEdit#Log QScrollBar::sub-line { height: 0; width: 0; }

QFrame#StatusBar {
  background: #0d1322;
  border-top: 1px solid #1e2942;
}
QLabel#StatusDot { font-size: 11px; }
QLabel#StatusText { color: #8b93a7; font-size: 12px; }
QLabel#StatusMeta { color: #4b5468; font-size: 11px; }

QFrame#TitleBar { background: transparent; }
QLabel#Title { color: #e6e9f0; font-size: 13.5px; font-weight: 700; letter-spacing: 2px; }
QLabel#TitleSub { color: #5b6475; font-size: 11px; letter-spacing: 1px; }
QLabel#TitleStatus { color: #5b6475; font-size: 11.5px; }
"""


# ---------------------------------------------------------------- 小部件

def _star_pixmap(size: int = 22, color="#c8aa6e") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = size / 2
    pts = []
    for i in range(8):
        ang = -math.pi / 2 + i * math.pi / 4
        r = c * 0.92 if i % 2 == 0 else c * 0.40
        pts.append((c + r * math.cos(ang), c + r * math.sin(ang)))
    path = QPainterPath()
    path.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    p.end()
    return pm


def _star_icon(size=22, color="#c8aa6e"):
    return QIcon(_star_pixmap(size, color))


def _glyph_pixmap(kind: str, size: int, color: str, weight: float = 1.7) -> QPixmap:
    """窗口控制图标：close=X, min=—，矢量绘制，圆头线条。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(weight)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m = size * 0.27
    c = size / 2
    if kind == "close":
        p.drawLine(QPointF(m, m), QPointF(size - m, size - m))
        p.drawLine(QPointF(size - m, m), QPointF(m, size - m))
    else:  # min
        p.drawLine(QPointF(m, c), QPointF(size - m, c))
    p.end()
    return pm


# ---------------------------------------------------------------- 标题栏

class TitleBar(QFrame):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self._win = win
        self._drag: QPoint | None = None
        self.setObjectName("TitleBar")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 0, 0)
        lay.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(_star_pixmap(20))
        title = QLabel("LEAGUE SKIN FANTOME BUILDER")
        title.setObjectName("Title")
        sub = QLabel("fantome 皮肤构建器")
        sub.setObjectName("TitleSub")
        lay.addWidget(logo)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch(1)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setStyleSheet("color:#5b6475;")
        self.status_txt = QLabel("就绪")
        self.status_txt.setObjectName("TitleStatus")
        lay.addWidget(self.status_dot)
        lay.addWidget(self.status_txt)
        lay.addStretch(1)

        icon = QSize(18, 18)
        btn_min = QPushButton()
        btn_min.setObjectName("WinBtn")
        btn_min.setIcon(QIcon(_glyph_pixmap("min", 18, "#9aa3b5")))
        btn_min.setIconSize(icon)
        btn_min.clicked.connect(self._win.showMinimized)
        btn_close = QPushButton()
        btn_close.setObjectName("CloseBtn")
        btn_close.setIcon(QIcon(_glyph_pixmap("close", 18, "#ff9aa8")))
        btn_close.setIconSize(icon)
        btn_close.clicked.connect(self._win.close)
        lay.addWidget(btn_min)
        lay.addWidget(btn_close)

    # 窗口拖拽
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and self._drag is not None:
            self._win.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


# ---------------------------------------------------------------- 主窗口

class MainWindow(QWidget):
    EDGE = 7

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LEAGUE SKIN FANTOME BUILDER — 英雄联盟皮肤 fantome 构建器")
        self.setWindowIcon(_star_icon(32))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMouseTracking(True)
        self.installEventFilter(self)
        self.setMinimumSize(880, 620)
        self.resize(1060, 780)
        self.setObjectName("Root")
        self.setStyleSheet(APP_QSS)

        self._resize_dir = 0
        self._last_len = 0
        self._cfg = load_config()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_titlebar())

        body = QHBoxLayout()
        body.setContentsMargins(22, 18, 22, 18)
        body.setSpacing(16)
        body.addLayout(self._build_left())
        body.addWidget(self._build_log_card(), 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_statusbar())

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(300)
        self._load_cfg()

    # ---------- 构建控件 ----------

    def _build_titlebar(self) -> TitleBar:
        tb = TitleBar(self)
        self.title_dot = tb.status_dot
        self.title_status = tb.status_txt
        return tb

    def _build_left(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(14)
        col.addWidget(self._card_path())
        col.addStretch(1)
        col.addLayout(self._build_actions())
        return col

    def _card_frame(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(8)
        accent = QLabel()
        accent.setFixedSize(3, 14)
        accent.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f0e6d2,stop:1 #a8823d);border-radius:1px;")
        t = QLabel(title)
        t.setObjectName("CardTitle")
        head.addWidget(accent)
        head.addWidget(t)
        head.addStretch(1)
        v.addLayout(head)
        return card

    def _card_path(self) -> QFrame:
        card = self._card_frame("路径设置")
        v = card.layout()

        v.addWidget(self._field_label("游戏安装目录", "（英雄联盟根目录，包含 Game 文件夹）"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.league_edit = QLineEdit()
        self.league_edit.setPlaceholderText("例如 C:\\Riot Games\\League of Legends")
        row.addWidget(self.league_edit, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.setObjectName("Ghost")
        btn_browse.clicked.connect(lambda: self._browse("league"))
        btn_check = QPushButton("检测")
        btn_check.setObjectName("Ghost")
        btn_check.clicked.connect(self._on_check)
        row.addWidget(btn_browse)
        row.addWidget(btn_check)
        v.addLayout(row)

        self.check_hint = QLabel("构建前请确认游戏已更新到最新版本")
        self.check_hint.setObjectName("Hint")
        v.addWidget(self.check_hint)

        v.addWidget(self._field_label("输出目录"))
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("留空 = 使用 程序目录/out")
        row2.addWidget(self.out_edit, 1)
        btn_out = QPushButton("浏览")
        btn_out.setObjectName("Ghost")
        btn_out.clicked.connect(lambda: self._browse("out"))
        row2.addWidget(btn_out)
        v.addLayout(row2)

        hint2 = QLabel("构建结果保存在 输出目录/skins/ 下")
        hint2.setObjectName("Hint")
        v.addWidget(hint2)
        return card

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_start = QPushButton("开始构建")
        self.btn_start.setObjectName("Primary")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("Danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        row.addWidget(self.btn_start, 1)
        row.addWidget(self.btn_stop)
        return row

    def _build_log_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        accent = QLabel()
        accent.setFixedSize(3, 14)
        accent.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f0e6d2,stop:1 #a8823d);border-radius:1px;")
        t = QLabel("构建日志")
        t.setObjectName("CardTitle")
        head.addWidget(accent)
        head.addWidget(t)
        head.addStretch(1)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("Ghost")
        self.btn_clear.clicked.connect(self._on_clear)
        head.addWidget(self.btn_clear)
        v.addLayout(head)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("Log")
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("等待构建…")
        self.log_edit.document().setMaximumBlockCount(3000)   # 防止海量日志把界面拖慢
        v.addWidget(self.log_edit, 1)
        return card

    def _build_statusbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 7, 22, 7)
        lay.setSpacing(8)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setStyleSheet("color:#5b6475;")
        self.status_text = QLabel("就绪")
        self.status_text.setObjectName("StatusText")
        meta = QLabel("构建引擎: build.py · 全部输出写本地 · 皮肤 mod 免费")
        meta.setObjectName("StatusMeta")
        lay.addWidget(self.status_dot)
        lay.addWidget(self.status_text)
        lay.addStretch(1)
        lay.addWidget(meta)
        return bar

    # ---------- 小工具 ----------

    def _field_label(self, text: str, sub: str = "") -> QLabel:
        lb = QLabel(f"{text}" + (f"  <span style='color:#4b5468'>{sub}</span>" if sub else ""))
        lb.setObjectName("FieldLabel")
        lb.setTextFormat(Qt.TextFormat.RichText)
        return lb

    def _load_cfg(self):
        c = self._cfg
        if c.get("league"):
            self.league_edit.setText(c["league"])
        if c.get("out"):
            self.out_edit.setText(c["out"])

    # ---------- 交互 ----------

    def _collect(self) -> dict:
        return {
            "league": self.league_edit.text().strip(),
            "out": self.out_edit.text().strip(),
            # 构建选项已移除界面，保持默认行为：包含炫彩、全部英雄、自动上限与线程
            "chromas": True,
            "refresh": False,
            "only": "",
            "limit": "",
            "workers": "",
        }

    def _browse(self, which: str):
        start = self.league_edit.text() if which == "league" else self.out_edit.text()
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", start or str(Path.home()))
        if not path:
            return
        if which == "league":
            self.league_edit.setText(path)
            self._set_hint("", "plain")
        else:
            self.out_edit.setText(path)

    def _set_hint(self, text: str, kind: str):
        self.check_hint.setText(text)
        self.check_hint.setProperty("ok", kind == "ok")
        self.check_hint.setProperty("err", kind == "err")
        self.check_hint.setStyleSheet("" if kind == "plain" else ("color:#3fb950;" if kind == "ok" else "color:#f85149;"))

    def _on_check(self):
        r = check_league(self.league_edit.text().strip())
        self._set_hint(r["msg"], "ok" if r["ok"] else "err")

    def _on_start(self):
        cfg = self._collect()
        if not cfg["league"]:
            QMessageBox.warning(self, "缺少路径", "请先填写游戏安装目录。")
            return
        try:
            ok, msg = start_build(cfg)
        except Exception as e:
            log_append(f"\n[启动构建异常] {e!r}\n")
            self._set_running_ui(False)
            QMessageBox.critical(self, "启动失败", f"发生异常:\n{e}")
            return
        if not ok:
            QMessageBox.warning(self, "无法开始", msg)
            return
        self.log_edit.clear()
        self._last_len = 0
        self._set_running_ui(True)

    def _on_stop(self):
        stop_build()

    def _on_clear(self):
        with _lock:
            state["log"] = ""
        self.log_edit.clear()
        self._last_len = 0

    def _set_running_ui(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_start.setText("构建中…" if running else "开始构建")
        self.btn_stop.setEnabled(running)
        if running:
            self._set_dot(self.title_dot, "#c8aa6e")
            self._set_dot(self.status_dot, "#c8aa6e")
            self.title_status.setText("构建中")
            self.status_text.setText("构建中 · 实时日志见右侧")
        else:
            st = state
            if st["exit_code"] == 0:
                self._set_dot(self.title_dot, "#3fb950")
                self._set_dot(self.status_dot, "#3fb950")
                self.title_status.setText("构建完成")
                self.status_text.setText("构建完成")
            else:
                self._set_dot(self.title_dot, "#f85149")
                self._set_dot(self.status_dot, "#f85149")
                self.title_status.setText("构建失败")
                self.status_text.setText("构建失败 / 已终止")

    @staticmethod
    def _set_dot(lb: QLabel, color: str):
        lb.setStyleSheet(f"color:{color};")

    # ---------- 轮询 ----------

    def _poll(self):
        st = state
        log = st["log"]
        if len(log) < self._last_len:
            self._last_len = 0
        if len(log) > self._last_len:
            self.log_edit.appendPlainText(log[self._last_len:])
            self._last_len = len(log)
            sb = self.log_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

        running = st["running"]
        if running != self.btn_stop.isEnabled():
            self._set_running_ui(running)
        if running:
            secs = int(time.time() - st["started_at"])
            self.status_text.setText(f"构建中 · 已用时 {secs // 60:02d}:{secs % 60:02d}")
            self.title_status.setText(f"构建中 {secs // 60:02d}:{secs % 60:02d}")

    # ---------- 无边框窗口缩放 ----------

    def eventFilter(self, obj, ev):
        if obj is self:
            t = ev.type()
            if t == QEvent.Type.MouseMove:
                pos = ev.position().toPoint()
                if ev.buttons() == Qt.MouseButton.NoButton:
                    self._update_cursor(pos)
                elif self._resize_dir:
                    self._apply_resize(ev.globalPosition().toPoint())
            elif t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._resize_dir = self._hit_test(ev.position().toPoint())
            elif t == QEvent.Type.MouseButtonRelease:
                self._resize_dir = 0
        return super().eventFilter(obj, ev)

    def _hit_test(self, pos: QPoint) -> int:
        r = self.rect()
        d = self.EDGE
        dirs = 0
        if pos.x() <= d:
            dirs |= 1          # W
        if pos.x() >= r.width() - d:
            dirs |= 2          # E
        if pos.y() <= d:
            dirs |= 4          # N
        if pos.y() >= r.height() - d:
            dirs |= 8          # S
        return dirs

    def _update_cursor(self, pos: QPoint):
        d = self._hit_test(pos)
        cur = {
            1 | 4: Qt.CursorShape.SizeFDiagCursor, 2 | 8: Qt.CursorShape.SizeFDiagCursor,
            2 | 4: Qt.CursorShape.SizeBDiagCursor, 1 | 8: Qt.CursorShape.SizeBDiagCursor,
            1: Qt.CursorShape.SizeHorCursor, 2: Qt.CursorShape.SizeHorCursor,
            4: Qt.CursorShape.SizeVerCursor, 8: Qt.CursorShape.SizeVerCursor,
        }.get(d, Qt.CursorShape.ArrowCursor)
        self.setCursor(cur)

    def _apply_resize(self, gpos: QPoint):
        g = self.geometry()
        d = self._resize_dir
        mw, mh = self.minimumWidth(), self.minimumHeight()
        if d & 4:  # 上
            top = min(gpos.y(), g.bottom() - mh)
            self.setGeometry(g.left(), top, g.width(), g.bottom() - top)
        elif d & 8:  # 下
            self.setGeometry(g.left(), g.top(), g.width(), max(gpos.y() - g.top(), mh))
        if d & 1:  # 左
            left = min(gpos.x(), g.right() - mw)
            self.setGeometry(left, self.y(), g.right() - left, self.height())
        elif d & 2:  # 右
            self.setGeometry(g.left(), self.y(), max(gpos.x() - g.left(), mw), self.height())

    # ---------- 关闭 ----------

    def closeEvent(self, e):
        if state["running"]:
            r = QMessageBox.question(
                self, "确认退出", "构建正在进行中，退出将终止构建。\n确定退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            stop_build()
            time.sleep(0.4)
        e.accept()


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
