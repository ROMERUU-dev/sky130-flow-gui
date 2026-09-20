"""Vector icons drawn with QPainter.

The navigation used bare Unicode glyphs (∿ ≣ ◫ ⌁ ≈ ⌂ ⚙). Coverage for those
varies by font, so some rendered as a dash or a box. Drawing them keeps the
look consistent everywhere and lets each icon follow the theme colour.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZE = 20


def _pen(painter: QPainter, color: QColor, width: float = 1.7) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    return pen


def _wave(painter: QPainter, r: QRectF, color: QColor) -> None:
    _pen(painter, color)
    path = QPainterPath()
    steps = 24
    for step in range(steps + 1):
        fraction = step / steps
        x = r.left() + r.width() * fraction
        y = r.center().y() - math.sin(fraction * 2 * math.pi) * r.height() * 0.32
        path.lineTo(x, y) if step else path.moveTo(x, y)
    painter.drawPath(path)


def _compare(painter: QPainter, r: QRectF, color: QColor) -> None:
    _pen(painter, color)
    for index in range(3):
        y = r.top() + r.height() * (0.2 + index * 0.3)
        painter.drawLine(QPointF(r.left(), y), QPointF(r.right() - r.width() * (index * 0.18), y))


def _layers(painter: QPainter, r: QRectF, color: QColor) -> None:
    _pen(painter, color)
    mid_x = r.center().x()
    for index in range(3):
        offset = r.top() + r.height() * (0.18 + index * 0.27)
        half = r.width() * 0.42
        quarter = r.height() * 0.13
        painter.drawPolygon([
            QPointF(mid_x, offset - quarter), QPointF(mid_x + half, offset),
            QPointF(mid_x, offset + quarter), QPointF(mid_x - half, offset),
        ])


def _bolt(painter: QPainter, r: QRectF, color: QColor) -> None:
    _pen(painter, color)
    path = QPainterPath()
    path.moveTo(r.center().x() + r.width() * 0.14, r.top())
    path.lineTo(r.left() + r.width() * 0.28, r.center().y() + r.height() * 0.06)
    path.lineTo(r.center().x(), r.center().y() + r.height() * 0.06)
    path.lineTo(r.center().x() - r.width() * 0.10, r.bottom())
    path.lineTo(r.right() - r.width() * 0.24, r.center().y() - r.height() * 0.04)
    path.lineTo(r.center().x(), r.center().y() - r.height() * 0.04)
    path.closeSubpath()
    painter.drawPath(path)


def _ruler(painter: QPainter, r: QRectF, color: QColor) -> None:
    """Two stacked current traces with an arrow: the EM sizing page."""
    _pen(painter, color)
    top = r.top() + r.height() * 0.24
    bottom = r.bottom() - r.height() * 0.24
    painter.drawLine(QPointF(r.left(), top), QPointF(r.right(), top))
    painter.drawLine(QPointF(r.left(), bottom), QPointF(r.right(), bottom))
    mid_y = r.center().y()
    painter.drawLine(QPointF(r.left() + r.width() * 0.12, mid_y), QPointF(r.right() - r.width() * 0.12, mid_y))
    tip = r.right() - r.width() * 0.12
    painter.drawLine(QPointF(tip, mid_y), QPointF(tip - r.width() * 0.18, mid_y - r.height() * 0.14))
    painter.drawLine(QPointF(tip, mid_y), QPointF(tip - r.width() * 0.18, mid_y + r.height() * 0.14))


def _folder(painter: QPainter, r: QRectF, color: QColor) -> None:
    _pen(painter, color)
    path = QPainterPath()
    path.moveTo(r.left(), r.bottom() - r.height() * 0.08)
    path.lineTo(r.left(), r.top() + r.height() * 0.22)
    path.lineTo(r.left() + r.width() * 0.4, r.top() + r.height() * 0.22)
    path.lineTo(r.left() + r.width() * 0.52, r.top() + r.height() * 0.38)
    path.lineTo(r.right(), r.top() + r.height() * 0.38)
    path.lineTo(r.right(), r.bottom() - r.height() * 0.08)
    path.closeSubpath()
    painter.drawPath(path)


def _gear(painter: QPainter, r: QRectF, color: QColor) -> None:
    _pen(painter, color, 1.5)
    center = r.center()
    radius = min(r.width(), r.height()) * 0.50
    ring = radius * 0.66
    for index in range(6):
        angle = index * math.pi / 3.0
        painter.drawLine(
            QPointF(center.x() + math.cos(angle) * ring, center.y() + math.sin(angle) * ring),
            QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius),
        )
    painter.drawEllipse(center, ring, ring)
    painter.drawEllipse(center, ring * 0.38, ring * 0.38)


_PAINTERS = {
    "simulation": _wave,
    "lvs": _compare,
    "extraction": _layers,
    "antenna": _bolt,
    "em": _ruler,
    "project": _folder,
    "preferences": _gear,
}


def make_icon(name: str, color: str, size: int = ICON_SIZE) -> QIcon:
    """Draw one navigation icon in the given colour."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    inset = size * 0.16
    rect = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    draw = _PAINTERS.get(name)
    if draw is not None:
        draw(painter, rect, QColor(color))
    painter.end()
    return QIcon(pixmap)


def make_menu_icon(color: str, size: int = ICON_SIZE) -> QIcon:
    """The hamburger used to collapse and expand the navigation."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    _pen(painter, QColor(color), 1.8)
    for index in range(3):
        y = size * (0.3 + index * 0.2)
        painter.drawLine(QPointF(size * 0.22, y), QPointF(size * 0.78, y))
    painter.end()
    return QIcon(pixmap)
