"""Professional startup splash screen for SKY130 Flow GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSplashScreen


def build_splash_pixmap(width: int = 920, height: int = 520) -> QPixmap:
    """Create a polished startup splash image using Qt painting."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    bg = QLinearGradient(0, 0, width, height)
    bg.setColorAt(0.0, QColor("#0b1220"))
    bg.setColorAt(0.45, QColor("#121f37"))
    bg.setColorAt(1.0, QColor("#0b0f19"))
    painter.fillRect(0, 0, width, height, bg)

    accent = QLinearGradient(0, height * 0.65, width, height)
    accent.setColorAt(0.0, QColor(0, 160, 255, 80))
    accent.setColorAt(1.0, QColor(0, 220, 180, 45))
    painter.fillRect(0, int(height * 0.65), width, int(height * 0.35), accent)

    painter.setPen(QPen(QColor("#28d7ff"), 2))
    painter.drawRoundedRect(20, 20, width - 40, height - 40, 22, 22)

    painter.setPen(QColor("#8be9fd"))
    painter.setFont(QFont("DejaVu Sans", 16, QFont.Bold))
    painter.drawText(55, 95, "SKY130 FLOW GUI")

    painter.setPen(QColor("#e2ecff"))
    painter.setFont(QFont("DejaVu Sans", 42, QFont.Black))
    painter.drawText(55, 170, "Analog / Custom IC")
    painter.drawText(55, 230, "Workflow Manager")

    painter.setPen(QColor("#97a7c3"))
    painter.setFont(QFont("DejaVu Sans", 14))
    painter.drawText(58, 285, "xschem · ngspice · magic · netgen · klayout")

    painter.setPen(QPen(QColor("#2ce0ff"), 3))
    x0 = width - 360
    y0 = 120
    painter.drawLine(x0, y0, x0 + 220, y0)
    painter.drawLine(x0, y0 + 40, x0 + 220, y0 + 40)
    painter.drawLine(x0, y0 + 80, x0 + 220, y0 + 80)
    painter.drawLine(x0, y0 + 120, x0 + 220, y0 + 120)
    painter.drawLine(x0, y0 + 160, x0 + 220, y0 + 160)

    painter.setPen(QColor("#9fc0ff"))
    painter.setFont(QFont("DejaVu Sans", 11))
    painter.drawText(width - 310, height - 70, "MVP · Linux Desktop")
    painter.drawText(width - 310, height - 45, "SKY130 oriented")

    painter.end()
    return pixmap


class StartupSplash(QSplashScreen):
    """Splash with bottom-right progress messages."""

    def __init__(self) -> None:
        super().__init__(build_splash_pixmap())
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

    def update_step(self, message: str) -> None:
        self.showMessage(
            message,
            alignment=Qt.AlignBottom | Qt.AlignRight,
            color=QColor("#d9f3ff"),
        )
