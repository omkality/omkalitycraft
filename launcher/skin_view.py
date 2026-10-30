"""Animated pixel-skin cuboids rendered by QPainter, without a web or GL runtime."""

import math
from typing import override

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QHideEvent,
    QImage,
    QPainter,
    QPolygonF,
    QShowEvent,
    QTransform,
)
from PySide6.QtWidgets import QWidget


def default_skin() -> QImage:
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.fillRect(0, 0, 32, 16, QColor("#ad7758"))
    painter.fillRect(8, 0, 8, 8, QColor("#3b3531"))
    painter.fillRect(0, 8, 8, 5, QColor("#3b3531"))
    painter.fillRect(16, 8, 8, 5, QColor("#3b3531"))
    painter.fillRect(24, 8, 8, 7, QColor("#3b3531"))
    painter.fillRect(8, 8, 8, 8, QColor("#d6a17c"))
    painter.fillRect(8, 8, 8, 2, QColor("#3b3531"))
    painter.fillRect(8, 10, 1, 2, QColor("#3b3531"))
    painter.fillRect(15, 10, 1, 2, QColor("#3b3531"))
    painter.fillRect(10, 11, 1, 1, QColor("#213b3c"))
    painter.fillRect(13, 11, 1, 1, QColor("#213b3c"))
    painter.fillRect(11, 14, 2, 1, QColor("#a2634a"))
    painter.fillRect(16, 16, 24, 16, QColor("#3c967a"))
    painter.fillRect(22, 20, 4, 4, QColor("#203d36"))
    for u, v in [(40, 16), (32, 48)]:
        painter.fillRect(u, v, 16, 16, QColor("#32856d"))
        painter.fillRect(u, v + 12, 16, 4, QColor("#d6a17c"))
    for u, v in [(0, 16), (16, 48)]:
        painter.fillRect(u, v, 16, 16, QColor("#293d4b"))
        painter.fillRect(u, v + 13, 16, 3, QColor("#1a282e"))
    painter.end()
    return image


class SkinView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.image = default_skin()
        self.model = "classic"
        self._angle = -25.0
        self.setMinimumSize(180, 245)
        self.setObjectName("skinPreview")
        self.animation = QPropertyAnimation(self, b"angle", self)
        self.animation.setStartValue(-25.0)
        self.animation.setEndValue(335.0)
        self.animation.setDuration(45000)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        self._angle = value
        self.update()

    angle = Property(float, get_angle, set_angle)

    def set_skin(self, png: bytes, model: str) -> None:
        image = QImage.fromData(png, "PNG")
        if image.isNull() or image.width() != 64 or image.height() not in {32, 64}:
            return
        self.image, self.model = image, model
        self.update()

    def _project(self, point: tuple[float, float, float]) -> tuple[QPointF, float]:
        x, y, z = point
        angle, pitch = math.radians(self._angle), math.radians(-12)
        rx, rz = x * math.cos(angle) + z * math.sin(angle), -x * math.sin(
            angle
        ) + z * math.cos(angle)
        ry, depth = (y - 16) * math.cos(pitch) - rz * math.sin(pitch), (
            y - 16
        ) * math.sin(pitch) + rz * math.cos(pitch)
        scale = min(self.width() / 25, self.height() / 38)
        return (
            QPointF(self.width() / 2 + rx * scale, self.height() / 2 + ry * scale),
            depth,
        )

    @staticmethod
    def _faces(
        x: float,
        y: float,
        z: float,
        w: float,
        h: float,
        d: float,
        u: int,
        v: int,
        padding: float = 0,
    ) -> list:
        x0, x1, y0, y1, z0, z1 = (
            x - padding,
            x + w + padding,
            y - padding,
            y + h + padding,
            z - padding,
            z + d + padding,
        )
        return [
            (
                [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
                (u + d, v + d, w, h),
            ),
            (
                [(x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1)],
                (u + 2 * d + w, v + d, w, h),
            ),
            (
                [(x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1)],
                (u, v + d, d, h),
            ),
            (
                [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)],
                (u + d + w, v + d, d, h),
            ),
            (
                [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)],
                (u + d, v, w, d),
            ),
            (
                [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
                (u + d + w, v, w, d),
            ),
        ]

    def _model_faces(self) -> list:
        arm = 3 if self.model == "slim" else 4
        modern = self.image.height() == 64
        parts = [
            (-4, 0, -4, 8, 8, 8, 0, 0),
            (-4, 8, -2, 8, 12, 4, 16, 16),
            (-4 - arm, 8, -2, arm, 12, 4, 40, 16),
            (4, 8, -2, arm, 12, 4, 32 if modern else 40, 48 if modern else 16),
            (-4, 20, -2, 4, 12, 4, 0, 16),
            (0, 20, -2, 4, 12, 4, 16 if modern else 0, 48 if modern else 16),
        ]
        faces = []
        for part in parts:
            faces.extend(self._faces(*part))
        faces.extend(self._faces(-4, 0, -4, 8, 8, 8, 32, 0, padding=0.25))
        if modern:
            for part in [
                (-4, 8, -2, 8, 12, 4, 16, 32),
                (-4 - arm, 8, -2, arm, 12, 4, 40, 32),
                (4, 8, -2, arm, 12, 4, 48, 48),
                (-4, 20, -2, 4, 12, 4, 0, 32),
                (0, 20, -2, 4, 12, 4, 0, 48),
            ]:
                faces.extend(self._faces(*part, padding=0.2))
        return faces

    @override
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(9, 19, 23, 85))
        painter.drawEllipse(
            QRectF(self.width() * 0.22, self.height() * 0.87, self.width() * 0.56, 13)
        )
        visible = []
        for points, uv in self._model_faces():
            projected = [self._project(point) for point in points]
            poly = [point for point, _ in projected]
            cross = (poly[1].x() - poly[0].x()) * (poly[2].y() - poly[1].y()) - (
                poly[1].y() - poly[0].y()
            ) * (poly[2].x() - poly[1].x())
            if cross <= 0:
                continue
            texture = self.image.copy(*[int(x) for x in uv])
            if texture.isNull():
                continue
            visible.append((sum(z for _, z in projected) / 4, poly, texture))
        for _, poly, texture in sorted(visible, key=lambda face: face[0], reverse=True):
            source = QPolygonF(
                [
                    QPointF(0, 0),
                    QPointF(texture.width(), 0),
                    QPointF(texture.width(), texture.height()),
                    QPointF(0, texture.height()),
                ]
            )
            transform = QTransform.quadToQuad(source, QPolygonF(poly))
            painter.save()
            painter.setTransform(transform)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(0, 0, texture)
            painter.restore()
        painter.end()

    @override
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.animation.start()

    @override
    def hideEvent(self, event: QHideEvent) -> None:
        self.animation.stop()
        super().hideEvent(event)
