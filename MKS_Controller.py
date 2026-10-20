from __future__ import annotations

import csv
import queue
import re
import sys
import threading
import time
import unicodedata
from collections import deque
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
import serial
import serial.tools.list_ports
from PyQt6.QtCore import QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLCDNumber,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "MKS Controller"
BAUDRATE = 115200
MAX_ARGON_SCCM = 4650.0
WINDOW_SECONDS = 60
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"

NUMBER = r"([-+]?\d+(?:[.,]\d+)?)"
RE_TARGET = re.compile(r"Objetivo\s+Ar\s*:\s*" + NUMBER, re.IGNORECASE)
RE_VOLTAGE = re.compile(r"V_MKS\s*:\s*" + NUMBER, re.IGNORECASE)
RE_MEASURED_N2 = re.compile(r"Flujo\s+Medido\s*\(\s*N2\s*\)\s*:\s*" + NUMBER, re.IGNORECASE)
RE_MEASURED_ARGON = re.compile(r"Flujo\s+Medido\s*\(\s*Argon\s*\)\s*:\s*" + NUMBER, re.IGNORECASE)
RE_EVENT_SETPOINT = re.compile(r"NUEVO\s+SET\s+POINT\s*:\s*" + NUMBER, re.IGNORECASE)
RE_EVENT_VOLTAGE = re.compile(
    r"Voltaje\s+SetPoint\s+MKS\s*:\s*" + NUMBER, re.IGNORECASE
)

STYLE = """
QWidget {
    color: #e6edf3;
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}
QWidget#Root {
    background-color: #0a0f15;
}
QScrollArea#ContentScroll {
    background: transparent;
    border: none;
}
QScrollArea#ContentScroll > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: #0a0f15;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #263445;
    min-height: 32px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #33465a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QFrame#Card {
    background-color: #111821;
    border: 1px solid #1e2a37;
    border-radius: 16px;
}
QFrame#Inset {
    background-color: #0c131b;
    border: 1px solid #1a2532;
    border-radius: 11px;
}
QFrame#VLine {
    background-color: #1e2a37;
    border: none;
}
QLabel {
    background: transparent;
}
QLabel#Logo {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0891b2, stop:1 #22d3ee);
    border-radius: 13px;
    color: #04141a;
    font-size: 22px;
    font-weight: 900;
}
QLabel#BrandTitle {
    color: #f4f8fc;
    font-size: 21px;
    font-weight: 800;
}
QLabel#BrandSub {
    color: #7d8b9c;
    font-size: 10px;
    font-weight: 600;
}
QLabel#SectionTitle {
    color: #9fb0c3;
    font-size: 11px;
    font-weight: 700;
}
QLabel#FieldHint {
    color: #6f8093;
    font-size: 10px;
    font-weight: 700;
}
QLabel#FieldLabel {
    color: #9fb0c3;
    font-size: 12px;
    font-weight: 600;
}
QLabel#Muted {
    color: #7d8b9c;
    font-size: 11px;
}
QLabel#Footer {
    color: #5f7083;
    font-size: 10px;
    font-weight: 600;
}
QLabel#Badge {
    background-color: #0c2831;
    color: #67e8f9;
    border: 1px solid #155e75;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#TargetValue {
    color: #22d3ee;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 17px;
    font-weight: 700;
}
QLabel#MetricTitle {
    color: #8fa2b6;
    font-size: 10px;
    font-weight: 700;
}
QLabel#MetricUnit {
    color: #617284;
    font-size: 10px;
    font-weight: 600;
}
QLabel#EventText {
    color: #b8c5d4;
    font-size: 12px;
}
QPushButton {
    background-color: #16202b;
    color: #e6edf3;
    border: 1px solid #263445;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #1b2836;
    border-color: #33465a;
}
QPushButton:pressed {
    background-color: #111a24;
}
QPushButton:disabled {
    color: #4f5f70;
    background-color: #0e151d;
    border-color: #1a2532;
}
QPushButton#Primary {
    background-color: #0891b2;
    border: 1px solid #22d3ee;
    color: #031318;
    font-weight: 700;
}
QPushButton#Primary:hover {
    background-color: #06b6d4;
}
QPushButton#Primary:pressed {
    background-color: #0e7490;
}
QPushButton#Danger {
    background-color: #b91c1c;
    border: 1px solid #ef4444;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#Danger:hover {
    background-color: #dc2626;
}
QPushButton#Danger:pressed {
    background-color: #991b1b;
}
QPushButton#Ghost {
    background-color: #0e151d;
    border: 1px solid #263445;
    color: #cbd5e1;
}
QPushButton#Ghost:hover {
    background-color: #16202b;
    border-color: #33465a;
}
QPushButton#Preset {
    background-color: #0e151d;
    border: 1px solid #263445;
    border-radius: 9px;
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 600;
    padding: 5px 4px;
}
QPushButton#Preset:hover {
    background-color: #132230;
    border-color: #0891b2;
    color: #67e8f9;
}
QComboBox {
    background-color: #0c131b;
    border: 1px solid #263445;
    border-radius: 10px;
    padding: 8px 34px 8px 12px;
    min-height: 20px;
    color: #dbe6f1;
}
QComboBox:hover {
    border-color: #33465a;
}
QComboBox:focus {
    border-color: #0891b2;
}
QComboBox:disabled {
    color: #5f7083;
    background-color: #0b1118;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 30px;
    border: none;
}
QComboBox::down-arrow {
    image: url("@ASSETS@/chevron-down.svg");
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background-color: #111821;
    border: 1px solid #263445;
    border-radius: 8px;
    selection-background-color: #0e7490;
    selection-color: #ffffff;
    padding: 4px;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    min-height: 26px;
    padding-left: 8px;
}
QDoubleSpinBox {
    background-color: #0c131b;
    border: 1px solid #263445;
    border-radius: 12px;
    padding: 8px 46px 8px 14px;
    color: #22d3ee;
    font-size: 24px;
    font-weight: 700;
    selection-background-color: #0891b2;
}
QDoubleSpinBox:focus {
    border: 1px solid #0891b2;
}
QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 34px;
    border-left: 1px solid #1e2a37;
    border-top-right-radius: 12px;
    background-color: #101923;
}
QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 34px;
    border-left: 1px solid #1e2a37;
    border-bottom-right-radius: 12px;
    background-color: #101923;
}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #16222e;
}
QDoubleSpinBox::up-arrow {
    image: url("@ASSETS@/chevron-up.svg");
    width: 11px;
    height: 11px;
}
QDoubleSpinBox::down-arrow {
    image: url("@ASSETS@/chevron-down.svg");
    width: 11px;
    height: 11px;
}
QCheckBox {
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 600;
    spacing: 9px;
    background: transparent;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #2b3948;
    background-color: #0c131b;
}
QCheckBox::indicator:hover {
    border-color: #0891b2;
}
QCheckBox::indicator:checked {
    background-color: #0891b2;
    border-color: #22d3ee;
    image: url("@ASSETS@/check.svg");
}
QLCDNumber {
    background: transparent;
    border: none;
}
QGraphicsView#Plot {
    border: 1px solid #1a2532;
    border-radius: 12px;
}
QToolTip {
    background-color: #111821;
    color: #dbe6f1;
    border: 1px solid #263445;
    padding: 6px;
}
"""


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def as_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_measurement(line: str) -> dict[str, float | None] | None:
    measured_match = RE_MEASURED_ARGON.search(line)
    if measured_match is None:
        return None
    target_match = RE_TARGET.search(line)
    voltage_match = RE_VOLTAGE.search(line)
    n2_match = RE_MEASURED_N2.search(line)
    return {
        "target_argon": as_float(target_match.group(1)) if target_match else None,
        "measured_argon": as_float(measured_match.group(1)),
        "voltage": as_float(voltage_match.group(1)) if voltage_match else None,
        "measured_n2": as_float(n2_match.group(1)) if n2_match else None,
    }


class CsvLogger:
    FIELDNAMES = ("Timestamp", "Target_Argon", "Measured_Argon", "Voltage_MKS")

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._handle = None
        self._writer = None
        self._path: Path | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def active(self) -> bool:
        return self._writer is not None

    def start(self) -> Path:
        self.close()
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.directory / f"mks_log_{stamp}.csv"
        counter = 2
        while path.exists():
            path = self.directory / f"mks_log_{stamp}_{counter}.csv"
            counter += 1
        handle = path.open("w", newline="", encoding="utf-8-sig")
        writer = csv.writer(handle)
        writer.writerow(self.FIELDNAMES)
        handle.flush()
        self._handle = handle
        self._writer = writer
        self._path = path
        return path

    def log(
        self,
        target: float | None,
        measured: float | None,
        voltage: float | None,
        timestamp: str,
    ) -> None:
        if self._writer is None:
            return
        self._writer.writerow(
            [
                timestamp,
                "" if target is None else f"{target:.1f}",
                "" if measured is None else f"{measured:.1f}",
                "" if voltage is None else f"{voltage:.3f}",
            ]
        )
        if self._handle is not None:
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None
        self._writer = None
        self._path = None


class SerialWorker(QThread):
    line_received = pyqtSignal(str)
    connection_changed = pyqtSignal(bool, str)
    error = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = BAUDRATE, parent=None) -> None:
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self._stop_event = threading.Event()
        self._tx: queue.Queue[str] = queue.Queue()
        self._serial: serial.Serial | None = None

    def send_command(self, command: str) -> None:
        if self.isRunning() and not self._stop_event.is_set():
            self._tx.put(str(command))

    def stop(self) -> None:
        self._stop_event.set()

    def _flush_commands(self) -> None:
        if self._serial is None or not self._serial.is_open:
            return
        while True:
            try:
                command = self._tx.get_nowait()
            except queue.Empty:
                return
            payload = command.strip()
            if payload:
                self._serial.write(f"{payload}\n".encode("utf-8"))

    def run(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=1.0,
            )
        except (serial.SerialException, OSError, ValueError) as exc:
            self.error.emit(f"No se pudo abrir {self.port}: {exc}")
            self.connection_changed.emit(False, "")
            return

        try:
            deadline = time.monotonic() + 1.0
            while not self._stop_event.is_set() and time.monotonic() < deadline:
                time.sleep(0.05)
            if self._stop_event.is_set():
                return

            self._serial.reset_input_buffer()
            self.connection_changed.emit(True, self.port)

            buffer = bytearray()
            while not self._stop_event.is_set():
                self._flush_commands()
                waiting = self._serial.in_waiting
                chunk = self._serial.read(waiting if waiting else 1)
                if not chunk:
                    continue
                buffer.extend(chunk)
                if len(buffer) > 32768:
                    buffer.clear()
                while b"\n" in buffer:
                    raw, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self.line_received.emit(line)
        except (serial.SerialException, OSError, ValueError) as exc:
            if not self._stop_event.is_set():
                self.error.emit(f"Se perdió la conexión con {self.port}: {exc}")
        finally:
            try:
                if self._serial is not None and self._serial.is_open:
                    self._serial.close()
            except (serial.SerialException, OSError):
                pass
            self.connection_changed.emit(False, "")


def build_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 128, 128)
    gradient.setColorAt(0.0, QColor("#0891b2"))
    gradient.setColorAt(1.0, QColor("#22d3ee"))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(6, 6, 116, 116, 30, 30)
    painter.setPen(QColor("#03131a"))
    painter.setFont(QFont("Segoe UI", 46, QFont.Weight.Black))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")
    painter.end()
    return QIcon(pixmap)


def restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class DashboardScroll(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setAutoFillBackground(False)

    def set_content(self, content: QWidget) -> None:
        self.setWidget(content)
        self._sync_content()
        QTimer.singleShot(0, self._sync_content)

    def _sync_content(self) -> None:
        content = self.widget()
        if content is None:
            return
        viewport = self.viewport().size()
        minimum = content.minimumSizeHint()
        content.resize(
            max(viewport.width(), minimum.width()),
            max(viewport.height(), minimum.height()),
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_content()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_content()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(build_icon())
        self.resize(1240, 820)
        self.setMinimumSize(1080, 720)

        self.worker: SerialWorker | None = None
        self.csv_logger = CsvLogger(LOGS_DIR)
        self._connected = False
        self._connecting = False
        self._manual_disconnect = False
        self._device_target = 0.0
        self._samples: deque[tuple[float, float, float]] = deque(maxlen=3600)
        self._t0: float | None = None
        self._last_sample_monotonic: float | None = None
        self._last_port_signature: tuple[tuple[str, str], ...] | None = None
        self._command_widgets: list[QWidget] = []

        self._build_ui()
        self._apply_styles()
        self._reset_monitoring()
        self._refresh_ports(force=True)
        self._apply_connection_ui(False)

        self._port_timer = QTimer(self)
        self._port_timer.setInterval(5000)
        self._port_timer.timeout.connect(self._auto_refresh_ports)
        self._port_timer.start()

        self._data_timer = QTimer(self)
        self._data_timer.setInterval(1000)
        self._data_timer.timeout.connect(self._check_data_freshness)
        self._data_timer.start()

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def _make_section_title(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("SectionTitle")
        font = label.font()
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        label.setFont(font)
        return label

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 10)
        outer.setSpacing(14)

        outer.addWidget(self._build_header())

        content = QHBoxLayout()
        content.setSpacing(16)

        left = QWidget()
        left.setFixedWidth(360)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(self._build_control_card())
        left_layout.addWidget(self._build_status_card())
        left_layout.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(16)

        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        measured_card, self.measured_lcd = self._build_metric(
            "FLUJO MEDIDO · AR", "sccm Argón", "#22d3ee", 6, 1
        )
        voltage_card, self.voltage_lcd = self._build_metric(
            "VOLTAJE MKS", "V reconstruido", "#a78bfa", 5, 3
        )
        n2_card, self.n2_lcd = self._build_metric(
            "FLUJO EQUIV. N2", "sccm N2", "#34d399", 6, 1
        )
        metrics.addWidget(measured_card, 1)
        metrics.addWidget(voltage_card, 1)
        metrics.addWidget(n2_card, 1)
        right.addLayout(metrics)

        right.addWidget(self._build_graph_card(), 1)
        right.addWidget(self._build_logging_card())

        content.addWidget(left)
        content.addLayout(right, 1)
        content.setContentsMargins(0, 0, 0, 0)

        content_widget = QWidget()
        content_widget.setObjectName("ContentArea")
        content_widget.setLayout(content)

        scroll = DashboardScroll()
        scroll.setObjectName("ContentScroll")
        scroll.set_content(content_widget)
        outer.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        self.footer_left = QLabel("MKS Controller  ·  ESP32  ·  115200 8N1")
        self.footer_left.setObjectName("Footer")
        self.footer_right = QLabel("Desconectado")
        self.footer_right.setObjectName("Footer")
        footer.addWidget(self.footer_left)
        footer.addStretch(1)
        footer.addWidget(self.footer_right)
        outer.addLayout(footer)

    def _build_header(self) -> QFrame:
        header = self._make_card()
        header.setFixedHeight(88)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(14)

        logo = QLabel("M")
        logo.setObjectName("Logo")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel('<span style="color:#22d3ee;">MKS</span> CONTROLLER')
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setObjectName("BrandTitle")
        subtitle = QLabel("CONTROL DE FLUJO DE ARGÓN  ·  ESP32")
        subtitle.setObjectName("BrandSub")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        layout.addLayout(brand)
        layout.addStretch(1)

        port_box = QVBoxLayout()
        port_box.setSpacing(4)
        port_label = QLabel("PUERTO SERIAL")
        port_label.setObjectName("FieldHint")
        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(270)
        self.port_combo.setMaximumWidth(330)
        self.port_combo.setFixedHeight(38)
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.refresh_button = QPushButton("Actualizar")
        self.refresh_button.setObjectName("Ghost")
        self.refresh_button.setFixedHeight(38)
        self.refresh_button.clicked.connect(lambda: self._refresh_ports(force=True))
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_button)
        port_box.addWidget(port_label)
        port_box.addLayout(port_row)
        layout.addLayout(port_box)

        self.connect_button = QPushButton("Conectar")
        self.connect_button.setObjectName("Primary")
        self.connect_button.setFixedSize(132, 40)
        self.connect_button.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_button, 0, Qt.AlignmentFlag.AlignBottom)

        self.status_pill = QFrame()
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setFixedHeight(34)
        self.status_pill.setMinimumWidth(140)
        pill_layout = QHBoxLayout(self.status_pill)
        pill_layout.setContentsMargins(12, 0, 12, 0)
        pill_layout.setSpacing(8)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_text = QLabel("DESCONECTADO")
        pill_layout.addWidget(self.status_dot)
        pill_layout.addWidget(self.status_text)
        pill_layout.addStretch(1)
        layout.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignBottom)

        return header

    def _build_control_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.addWidget(self._make_section_title("Control de flujo"))
        head.addStretch(1)
        badge = QLabel("0 – 4650 sccm")
        badge.setObjectName("Badge")
        head.addWidget(badge)
        layout.addLayout(head)

        field_label = QLabel("SET POINT DE ARGÓN")
        field_label.setObjectName("FieldLabel")
        layout.addWidget(field_label)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(0.0, MAX_ARGON_SCCM)
        self.spin.setDecimals(1)
        self.spin.setSingleStep(10.0)
        self.spin.setSuffix(" sccm")
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spin.setKeyboardTracking(False)
        self.spin.setAccelerated(True)
        self.spin.setFixedHeight(52)
        self.spin.lineEdit().returnPressed.connect(self.send_setpoint)
        layout.addWidget(self.spin)

        self.set_button = QPushButton("Establecer flujo")
        self.set_button.setObjectName("Primary")
        self.set_button.setFixedHeight(38)
        self.set_button.clicked.connect(self.send_setpoint)
        layout.addWidget(self.set_button)

        self.emergency_button = QPushButton("Cierre de emergencia  ·  0 sccm")
        self.emergency_button.setObjectName("Danger")
        self.emergency_button.setFixedHeight(40)
        self.emergency_button.clicked.connect(self.emergency_stop)
        layout.addWidget(self.emergency_button)

        preset_label = QLabel("PRESETS RÁPIDOS")
        preset_label.setObjectName("FieldLabel")
        layout.addWidget(preset_label)

        preset_grid = QGridLayout()
        preset_grid.setSpacing(6)
        for index, value in enumerate((0, 100, 500, 1000, 2500, 4650)):
            button = QPushButton(f"{value} sccm")
            button.setObjectName("Preset")
            button.setFixedHeight(32)
            button.clicked.connect(
                lambda _checked=False, preset=float(value): self.apply_preset(preset)
            )
            preset_grid.addWidget(button, index // 3, index % 3)
            self._command_widgets.append(button)
        layout.addLayout(preset_grid)

        target_box = QFrame()
        target_box.setObjectName("Inset")
        target_layout = QHBoxLayout(target_box)
        target_layout.setContentsMargins(12, 7, 12, 7)
        target_layout.setSpacing(8)
        target_label = QLabel("SET POINT ACTIVO")
        target_label.setObjectName("FieldHint")
        self.target_value = QLabel("—")
        self.target_value.setObjectName("TargetValue")
        target_layout.addWidget(target_label)
        target_layout.addStretch(1)
        target_layout.addWidget(self.target_value)
        layout.addWidget(target_box)

        self._command_widgets.extend([self.set_button, self.emergency_button])
        return card

    def _build_status_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)
        layout.addWidget(self._make_section_title("Estado del dispositivo"))

        event_box = QFrame()
        event_box.setObjectName("Inset")
        event_layout = QVBoxLayout(event_box)
        event_layout.setContentsMargins(12, 8, 12, 8)
        event_layout.setSpacing(3)
        self.event_label = QLabel("Sin eventos del dispositivo")
        self.event_label.setObjectName("EventText")
        self.event_label.setWordWrap(True)
        self.event_label.setMinimumHeight(36)
        self.event_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.event_time = QLabel("—")
        self.event_time.setObjectName("Muted")
        event_layout.addWidget(self.event_label)
        event_layout.addWidget(self.event_time)
        layout.addWidget(event_box)
        return card

    def _build_metric(
        self,
        title: str,
        unit: str,
        accent: str,
        digits: int,
        decimals: int,
    ) -> tuple[QFrame, QLCDNumber]:
        card = self._make_card()
        card.setFixedHeight(126)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(4)

        head = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background-color:{accent}; border-radius:3px;")
        head.addWidget(title_label)
        head.addStretch(1)
        head.addWidget(dot)
        layout.addLayout(head)

        lcd = QLCDNumber()
        lcd.setDigitCount(digits)
        lcd.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        lcd.setFrameShape(QFrame.Shape.NoFrame)
        lcd.setSmallDecimalPoint(False)
        lcd.setMinimumHeight(58)
        lcd.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lcd.setStyleSheet(
            f"color:{accent}; background:transparent; border:none;"
        )
        palette = lcd.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(accent))
        lcd.setPalette(palette)
        lcd.display(f"{0.0:.{decimals}f}")
        layout.addWidget(lcd, 1)

        footer = QHBoxLayout()
        unit_label = QLabel(unit)
        unit_label.setObjectName("MetricUnit")
        live_label = QLabel("EN VIVO")
        live_label.setObjectName("MetricUnit")
        footer.addWidget(unit_label)
        footer.addStretch(1)
        footer.addWidget(live_label)
        layout.addLayout(footer)

        return card, lcd

    def _build_graph_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self._make_section_title("Flujo en tiempo real"))
        head.addSpacing(12)

        measured_swatch = QFrame()
        measured_swatch.setFixedSize(18, 4)
        measured_swatch.setStyleSheet("background-color:#22d3ee; border-radius:2px;")
        measured_legend = QLabel("Flujo medido")
        measured_legend.setObjectName("MetricUnit")
        head.addWidget(measured_swatch)
        head.addWidget(measured_legend)
        head.addSpacing(10)

        target_swatch = QFrame()
        target_swatch.setFixedSize(18, 4)
        target_swatch.setStyleSheet("border-top:2px dashed #f59e0b;")
        target_legend = QLabel("Set point")
        target_legend.setObjectName("MetricUnit")
        head.addWidget(target_swatch)
        head.addWidget(target_legend)
        head.addStretch(1)
        self.graph_status = QLabel("SIN CONEXIÓN")
        self.graph_status.setStyleSheet(
            "color:#617284; font-size:10px; font-weight:700;"
        )
        head.addWidget(self.graph_status)
        badge = QLabel("60 s")
        badge.setObjectName("Badge")
        head.addWidget(badge)
        layout.addLayout(head)

        pg.setConfigOptions(antialias=True)
        self.plot = pg.PlotWidget(background="#0b1118")
        self.plot.setObjectName("Plot")
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=True)
        self.plot.showGrid(x=True, y=True, alpha=0.12)
        self.plot.setLabel("bottom", "Tiempo", units="s", color="#7d8b9c", size="9pt")
        self.plot.setLabel("left", "Flujo", units="sccm", color="#7d8b9c", size="9pt")
        for axis_name in ("left", "bottom"):
            axis = self.plot.getAxis(axis_name)
            axis.setPen(pg.mkPen("#263241", width=1))
            axis.setTextPen(pg.mkPen("#7d8b9c"))
            axis.setStyle(
                tickFont=QFont("Segoe UI", 8),
                tickTextOffset=6,
                autoExpandTextSpace=True,
            )
        self.plot.setLimits(yMin=0)
        self.plot.enableAutoRange(axis="y")
        self.plot.setXRange(0, WINDOW_SECONDS, padding=0)
        self.plot.setMinimumHeight(190)

        self.measured_curve = self.plot.plot(
            pen=pg.mkPen("#22d3ee", width=2.4),
            fillLevel=0,
            brush=pg.mkBrush(34, 211, 238, 26),
        )
        self.target_curve = self.plot.plot(
            pen=pg.mkPen("#f59e0b", width=1.4, style=Qt.PenStyle.DashLine),
        )
        layout.addWidget(self.plot, 1)
        return card

    def _build_logging_card(self) -> QFrame:
        card = self._make_card()
        card.setFixedHeight(72)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        self.log_checkbox = QCheckBox("Grabar datos en CSV")
        self.log_checkbox.toggled.connect(self._on_log_toggle)
        layout.addWidget(self.log_checkbox)

        divider = QFrame()
        divider.setObjectName("VLine")
        divider.setFixedWidth(1)
        divider.setFixedHeight(36)
        layout.addWidget(divider)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.log_path_label = QLabel("Sin archivo activo")
        self.log_path_label.setObjectName("Muted")
        self.log_hint_label = QLabel(
            "Timestamp · Target_Argon · Measured_Argon · Voltage_MKS"
        )
        self.log_hint_label.setStyleSheet("color:#617284; font-size:10px;")
        info.addWidget(self.log_path_label)
        info.addWidget(self.log_hint_label)
        layout.addLayout(info, 1)

        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.setFixedHeight(36)
        self.open_folder_button.clicked.connect(self._open_logs_folder)
        layout.addWidget(self.open_folder_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _apply_styles(self) -> None:
        self.setStyleSheet(STYLE.replace("@ASSETS@", ASSETS_DIR.as_posix()))

    def _refresh_ports(self, force: bool = False) -> None:
        try:
            ports = sorted(
                serial.tools.list_ports.comports(),
                key=lambda item: item.device or "",
            )
        except Exception:
            ports = []

        items = tuple(
            (port.device, f"{port.device}  ·  {port.description}")
            for port in ports
        )
        if not force and items == self._last_port_signature:
            return

        current = self.port_combo.currentData()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        if not items:
            self.port_combo.addItem("No se detectaron puertos", None)
        else:
            for device, label in items:
                self.port_combo.addItem(label, device)
            devices = [device for device, _ in items]
            index = devices.index(current) if current in devices else 0
            if current not in devices:
                for position, port in enumerate(ports):
                    description = (port.description or "").upper()
                    if any(
                        keyword in description
                        for keyword in (
                            "CP210",
                            "CH340",
                            "CH910",
                            "USB-SERIAL",
                            "ESP32",
                            "UART",
                        )
                    ):
                        index = position
                        break
            self.port_combo.setCurrentIndex(index)
        self.port_combo.blockSignals(False)
        self._last_port_signature = items
        self.refresh_button.setToolTip(f"{len(items)} puerto(s) detectado(s)")
        if not self._connected and not self._connecting:
            self.connect_button.setEnabled(bool(items))

    def _auto_refresh_ports(self) -> None:
        if not self._connected and not self._connecting:
            self._refresh_ports()

    def _style_status(self, state: str, text: str) -> None:
        palette = {
            "connected": ("#34d399", "#34d399", "#07251d", "#065f46", "#6ee7b7"),
            "connecting": ("#fbbf24", "#fbbf24", "#2a2210", "#92400e", "#fcd34d"),
            "disconnected": ("#ef4444", "#ef4444", "#2a1214", "#7f1d1d", "#fca5a5"),
            "error": ("#ef4444", "#ef4444", "#2a1214", "#7f1d1d", "#fca5a5"),
        }
        dot, _, background, border, foreground = palette.get(
            state, palette["disconnected"]
        )
        self.status_pill.setStyleSheet(
            f"QFrame#StatusPill {{ background-color:{background}; "
            f"border:1px solid {border}; border-radius:16px; }}"
        )
        self.status_dot.setStyleSheet(
            f"background-color:{dot}; border-radius:4px;"
        )
        self.status_text.setText(text)
        self.status_text.setStyleSheet(
            f"color:{foreground}; font-size:10px; font-weight:800; "
            "background:transparent;"
        )

    def _apply_connection_ui(self, connected: bool, connecting: bool = False) -> None:
        self._connected = connected
        self._connecting = connecting

        if connecting:
            self._style_status("connecting", "CONECTANDO")
            self.connect_button.setText("Conectando…")
            self.connect_button.setObjectName("Ghost")
            restyle(self.connect_button)
            self.connect_button.setEnabled(False)
            self.port_combo.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.footer_right.setText("Abriendo puerto serie…")
        elif connected:
            self._style_status("connected", "CONECTADO")
            self.connect_button.setText("Desconectar")
            self.connect_button.setObjectName("Ghost")
            restyle(self.connect_button)
            self.connect_button.setEnabled(True)
            self.port_combo.setEnabled(False)
            self.refresh_button.setEnabled(False)
            port = self.port_combo.currentData() or ""
            self.footer_right.setText(f"Conectado a {port}  ·  115200 8N1")
        else:
            self._style_status("disconnected", "DESCONECTADO")
            self.connect_button.setText("Conectar")
            self.connect_button.setObjectName("Primary")
            restyle(self.connect_button)
            has_port = self.port_combo.currentData() is not None
            self.connect_button.setEnabled(has_port)
            self.port_combo.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.footer_right.setText("Desconectado  ·  115200 8N1")

        for widget in self._command_widgets:
            widget.setEnabled(connected)

    def toggle_connection(self) -> None:
        if self._connecting:
            return
        if self._connected:
            self._disconnect_serial()
        else:
            self._connect_serial()

    def _connect_serial(self) -> None:
        port = self.port_combo.currentData()
        if not port:
            self._set_event("No hay un puerto serie seleccionado.", "warn")
            return

        self._clear_monitoring()
        self._apply_connection_ui(False, connecting=True)

        worker = SerialWorker(port, BAUDRATE, self)
        self.worker = worker
        worker.line_received.connect(self._on_line)
        worker.connection_changed.connect(self._on_connection_changed)
        worker.error.connect(self._on_serial_error)
        worker.start()

    def _disconnect_serial(self) -> None:
        self._manual_disconnect = True
        self._set_event("Cerrando puerto serie…", "info")
        if self.worker is not None and self.worker.isRunning():
            self._style_status("connecting", "DESCONECTANDO")
            self.connect_button.setEnabled(False)
            self.footer_right.setText("Cerrando puerto serie…")
            self.worker.stop()
        else:
            self._apply_connection_ui(False)
            self._clear_monitoring()
            self._manual_disconnect = False
            self._set_event("Puerto serie desconectado.", "info")

    def _on_connection_changed(self, connected: bool, detail: str) -> None:
        if connected:
            self._apply_connection_ui(True)
            self._set_live_state("ESPERANDO LECTURAS", "#617284")
            if self.csv_logger.active:
                self.log_hint_label.setText("Grabando datos cada lectura…")
                self.log_hint_label.setStyleSheet("color:#34d399; font-size:10px;")
            self._set_event(
                f"Conectado a {detail}  ·  ESP32 listo para recibir comandos.", "ok"
            )
            return

        manual = self._manual_disconnect
        self._manual_disconnect = False
        self._connecting = False
        self._apply_connection_ui(False)
        self._clear_monitoring()
        if self.worker is not None:
            self.worker.wait(1000)
            self.worker.deleteLater()
            self.worker = None
        if self.csv_logger.active:
            self.log_hint_label.setText("Grabación en pausa · esperando conexión")
            self.log_hint_label.setStyleSheet("color:#fbbf24; font-size:10px;")
        if manual:
            self._set_event("Puerto serie desconectado.", "info")
        self._refresh_ports(force=True)

    def _on_serial_error(self, message: str) -> None:
        self._set_event(message, "danger")
        self._style_status("error", "ERROR")
        self.footer_right.setText(message)
        self._set_live_state("ERROR DE COMUNICACIÓN", "#f87171")

    def _on_line(self, line: str) -> None:
        normalized = strip_accents(line)
        measurement = parse_measurement(normalized)
        if measurement is not None:
            self._handle_measurement(measurement)
            return

        upper = normalized.upper()
        if "NUEVO SET POINT" in upper:
            target_match = RE_EVENT_SETPOINT.search(normalized)
            voltage_match = RE_EVENT_VOLTAGE.search(normalized)
            if target_match is not None:
                target = as_float(target_match.group(1))
                self._device_target = target
                self.target_value.setText(f"{target:.1f} sccm")
                message = f"Nuevo set point confirmado: {target:.1f} sccm"
                if voltage_match is not None:
                    volts = as_float(voltage_match.group(1))
                    message += f"  ·  {volts:.3f} V en DAC"
                self._set_event(message, "ok")
            else:
                self._set_event(line, "info")
        elif "VALVULA CERRADA" in upper:
            self._device_target = 0.0
            self.target_value.setText("0.0 sccm")
            self._set_event("Válvula cerrada · flujo cortado (0 sccm).", "danger")
        elif "AVISO" in upper:
            self._set_event(line, "warn")

    def _handle_measurement(self, data: dict[str, float | None]) -> None:
        now = datetime.now()
        monotonic_now = time.monotonic()
        if self._t0 is None:
            self._t0 = monotonic_now
        elapsed = monotonic_now - self._t0

        measured = data["measured_argon"]
        voltage = data["voltage"]
        n2 = data["measured_n2"]
        target = data["target_argon"]
        if target is None:
            target = self._device_target
        else:
            self._device_target = target
            self.target_value.setText(f"{target:.1f} sccm")

        if measured is not None:
            self.measured_lcd.display(f"{measured:.1f}")
        if voltage is not None:
            self.voltage_lcd.display(f"{voltage:.3f}")
        if n2 is not None:
            self.n2_lcd.display(f"{n2:.1f}")

        self._samples.append((elapsed, measured or 0.0, target))
        cutoff = elapsed - (WINDOW_SECONDS + 2)
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        xs = [sample[0] for sample in self._samples]
        measured_values = [sample[1] for sample in self._samples]
        target_values = [sample[2] for sample in self._samples]
        self.measured_curve.setData(xs, measured_values)
        self.target_curve.setData(xs, target_values)

        x_end = max(float(WINDOW_SECONDS), elapsed)
        self.plot.setXRange(max(0.0, x_end - WINDOW_SECONDS), x_end, padding=0)

        self._last_sample_monotonic = monotonic_now
        self._set_live_state("EN VIVO · VENTANA 60 s", "#34d399")
        self.csv_logger.log(
            target,
            measured,
            voltage,
            now.isoformat(timespec="milliseconds"),
        )

    def send_setpoint(self) -> None:
        if not self._connected or self.worker is None:
            return
        value = round(float(self.spin.value()), 1)
        self.worker.send_command(f"{value:.1f}")
        self._device_target = value
        self.target_value.setText(f"{value:.1f} sccm")
        self._set_event(f"Comando enviado: {value:.1f} sccm de Argón.", "info")

    def emergency_stop(self) -> None:
        if not self._connected or self.worker is None:
            return
        self.worker.send_command("0")
        self.spin.setValue(0.0)
        self._device_target = 0.0
        self.target_value.setText("0.0 sccm")
        self._set_event("Cierre de emergencia enviado · válvula cerrada.", "danger")

    def apply_preset(self, value: float) -> None:
        self.spin.setValue(value)
        self.send_setpoint()

    def _set_event(self, message: str, level: str = "info") -> None:
        colors = {
            "ok": "#34d399",
            "info": "#93c5fd",
            "warn": "#fbbf24",
            "danger": "#f87171",
        }
        self.event_label.setText(message)
        self.event_label.setStyleSheet(
            f"color:{colors.get(level, '#b8c5d4')}; font-size:12px;"
        )
        self.event_time.setText(datetime.now().strftime("Último evento · %H:%M:%S"))

    def _set_live_state(self, text: str, color: str) -> None:
        self.graph_status.setText(text)
        self.graph_status.setStyleSheet(
            f"color:{color}; font-size:10px; font-weight:700;"
        )

    def _check_data_freshness(self) -> None:
        if not self._connected or self._last_sample_monotonic is None:
            return
        age = time.monotonic() - self._last_sample_monotonic
        if age > 3.0:
            self._set_live_state("SIN DATOS RECIENTES", "#fbbf24")
        else:
            self._set_live_state("EN VIVO · VENTANA 60 s", "#34d399")

    def _clear_monitoring(self) -> None:
        self._samples.clear()
        self._t0 = None
        self._last_sample_monotonic = None
        self.measured_curve.setData([], [])
        self.target_curve.setData([], [])
        self.measured_lcd.display("0.0")
        self.voltage_lcd.display("0.000")
        self.n2_lcd.display("0.0")
        self.target_value.setText("—")
        self._set_live_state("SIN CONEXIÓN", "#617284")

    def _reset_monitoring(self) -> None:
        self._clear_monitoring()
        self.event_label.setText("Sin eventos del dispositivo")
        self.event_label.setStyleSheet("color:#b8c5d4; font-size:12px;")
        self.event_time.setText("—")

    def _on_log_toggle(self, checked: bool) -> None:
        if checked:
            try:
                path = self.csv_logger.start()
            except OSError as exc:
                self.log_checkbox.blockSignals(True)
                self.log_checkbox.setChecked(False)
                self.log_checkbox.blockSignals(False)
                self.log_path_label.setText("Sin archivo activo")
                self._set_event(f"No se pudo iniciar el registro: {exc}", "danger")
                return
            relative = path.relative_to(BASE_DIR).as_posix()
            self.log_path_label.setText(f"Archivo: {relative}")
            self.log_path_label.setToolTip(str(path))
            if self._connected:
                self.log_hint_label.setText("Grabando datos cada lectura…")
                self.log_hint_label.setStyleSheet("color:#34d399; font-size:10px;")
            else:
                self.log_hint_label.setText("Grabación en espera · conecta el ESP32")
                self.log_hint_label.setStyleSheet("color:#fbbf24; font-size:10px;")
            self._set_event(f"Registro CSV iniciado: {path.name}", "ok")
        else:
            self.csv_logger.close()
            self.log_path_label.setText("Sin archivo activo")
            self.log_path_label.setToolTip("")
            self.log_hint_label.setText(
                "Timestamp · Target_Argon · Measured_Argon · Voltage_MKS"
            )
            self.log_hint_label.setStyleSheet("color:#617284; font-size:10px;")
            self._set_event("Registro CSV detenido.", "info")

    def _open_logs_folder(self) -> None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS_DIR)))
        except OSError as exc:
            self._set_event(f"No se pudo abrir la carpeta: {exc}", "danger")

    def closeEvent(self, event) -> None:
        self._port_timer.stop()
        self._data_timer.stop()
        self.csv_logger.close()
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(1500)
            self.worker.deleteLater()
            self.worker = None
        super().closeEvent(event)


def main() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "LEOLAB.MKSController"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("LEOLAB")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
