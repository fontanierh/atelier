"""Local planar transforms shared by hero placement data."""
import math


def local(cx, cy, yaw, lx, ly):
    a = math.radians(yaw)
    return cx + lx * math.cos(a) - ly * math.sin(a), cy + lx * math.sin(a) + ly * math.cos(a)
