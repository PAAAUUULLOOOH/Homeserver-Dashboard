"""Small bounded vector caches; no raster or device-resolution conversion."""
from functools import lru_cache
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath


@lru_cache(maxsize=256)
def _rounded(x, y, width, height, radius):
    path=QPainterPath()
    path.addRoundedRect(QRectF(x,y,width,height),radius,radius)
    return path


def rounded(rect, radius):
    # Return a value copy so a caller can safely extend/detach its path.
    return QPainterPath(_rounded(rect.x(),rect.y(),rect.width(),rect.height(),radius))

