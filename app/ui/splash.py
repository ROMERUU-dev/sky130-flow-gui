"""Professional startup splash screen for SKY130 Flow GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSplashScreen


SPLASH_PRIMARY = QColor("#0a5c2a")
SPLASH_SECONDARY = QColor("#0f7a38")
SPLASH_DARK = QColor("#062816")
SPLASH_ACCENT = QColor("#9cf5b4")
SPLASH_TEXT = QColor("#f4fff7")
SPLASH_MUTED = QColor("#d3ebd9")
SPLASH_PROGRESS = QColor("#e9fff0")
LOGO_PATH = Path("/home/romeruu/Descargas/ardilla_silueta_blanca_suave.svg")


def _draw_fallback_logo(painter: QPainter, x: int, y: int, scale: float = 1.0) -> None:
    """Fallback logo used only if the SVG cannot be loaded."""
    path = QPainterPath()
    path.moveTo(x + 30 * scale, y + 140 * scale)
    path.cubicTo(x + 10 * scale, y + 90 * scale, x + 30 * scale, y + 40 * scale, x + 80 * scale, y + 35 * scale)
    path.cubicTo(x + 110 * scale, y + 15 * scale, x + 150 * scale, y + 18 * scale, x + 170 * scale, y + 40 * scale)
    path.cubicTo(x + 190 * scale, y + 65 * scale, x + 188 * scale, y + 92 * scale, x + 173 * scale, y + 114 * scale)
    path.cubicTo(x + 198 * scale, y + 114 * scale, x + 219 * scale, y + 130 * scale, x + 228 * scale, y + 150 * scale)
    path.cubicTo(x + 245 * scale, y + 192 * scale, x + 228 * scale, y + 238 * scale, x + 188 * scale, y + 254 * scale)
    path.cubicTo(x + 164 * scale, y + 264 * scale, x + 128 * scale, y + 264 * scale, x + 103 * scale, y + 254 * scale)
    path.cubicTo(x + 65 * scale, y + 238 * scale, x + 50 * scale, y + 212 * scale, x + 49 * scale, y + 175 * scale)
    path.cubicTo(x + 45 * scale, y + 170 * scale, x + 40 * scale, y + 157 * scale, x + 30 * scale, y + 140 * scale)

    tail = QPainterPath()
    tail.moveTo(x + 202 * scale, y + 70 * scale)
    tail.cubicTo(x + 230 * scale, y + 10 * scale, x + 310 * scale, y + 0 * scale, x + 360 * scale, y + 50 * scale)
    tail.cubicTo(x + 397 * scale, y + 88 * scale, x + 406 * scale, y + 137 * scale, x + 394 * scale, y + 182 * scale)
    tail.cubicTo(x + 380 * scale, y + 171 * scale, x + 361 * scale, y + 165 * scale, x + 339 * scale, y + 165 * scale)
    tail.cubicTo(x + 315 * scale, y + 165 * scale, x + 294 * scale, y + 173 * scale, x + 278 * scale, y + 190 * scale)
    tail.cubicTo(x + 282 * scale, y + 146 * scale, x + 260 * scale, y + 102 * scale, x + 202 * scale, y + 70 * scale)

    leg = QPainterPath()
    leg.moveTo(x + 95 * scale, y + 255 * scale)
    leg.cubicTo(x + 88 * scale, y + 280 * scale, x + 84 * scale, y + 305 * scale, x + 88 * scale, y + 325 * scale)
    leg.lineTo(x + 126 * scale, y + 325 * scale)
    leg.cubicTo(x + 132 * scale, y + 304 * scale, x + 130 * scale, y + 279 * scale, x + 121 * scale, y + 255 * scale)

    painter.fillPath(tail, QColor("#f6fbff"))
    painter.fillPath(path, QColor("#ffffff"))
    painter.fillPath(leg, QColor("#ffffff"))


def _draw_logo(painter: QPainter, rect: QRectF) -> None:
    """Draw the app SVG logo, falling back to a simple vector mark."""
    clip_path = QPainterPath()
    clip_path.addRoundedRect(rect, 26, 26)
    painter.save()
    painter.setClipPath(clip_path)

    renderer = QSvgRenderer(str(LOGO_PATH))
    if renderer.isValid():
        renderer.render(painter, rect)
        painter.restore()
        return

    _draw_fallback_logo(painter, x=int(rect.x()), y=int(rect.y()), scale=rect.width() / 380.0)
    painter.restore()


def build_splash_pixmap(width: int = 1020, height: int = 520) -> QPixmap:
    """Create a polished startup splash image using Qt painting."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    bg = QLinearGradient(0, 0, width, height)
    bg.setColorAt(0.0, SPLASH_DARK)
    bg.setColorAt(0.45, SPLASH_PRIMARY)
    bg.setColorAt(1.0, QColor("#04180d"))
    painter.fillRect(0, 0, width, height, bg)

    accent = QLinearGradient(0, height * 0.65, width, height)
    accent.setColorAt(0.0, QColor(120, 255, 170, 55))
    accent.setColorAt(1.0, QColor(255, 255, 255, 22))
    painter.fillRect(0, int(height * 0.65), width, int(height * 0.35), accent)

    painter.setPen(QPen(SPLASH_ACCENT, 2))
    painter.drawRoundedRect(20, 20, width - 40, height - 40, 22, 22)

    _draw_logo(painter, QRectF(728, 114, 195, 235))

    painter.setPen(SPLASH_ACCENT)
    painter.setFont(QFont("DejaVu Sans", 18, QFont.Bold))
    painter.drawText(55, 95, "SKY130 FLOW GUI")

    painter.setPen(SPLASH_TEXT)
    painter.setFont(QFont("DejaVu Sans", 45, QFont.Black))
    painter.drawText(55, 170, "Analog & Custom IC")
    painter.drawText(55, 235, "Workflow Manager")

    painter.setPen(SPLASH_MUTED)
    painter.setFont(QFont("DejaVu Sans", 15))
    painter.drawText(58, 300, "xschem · ngspice · magic · netgen · klayout")

    painter.setPen(QColor("#d6ffe2"))
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
            color=SPLASH_PROGRESS,
        )
