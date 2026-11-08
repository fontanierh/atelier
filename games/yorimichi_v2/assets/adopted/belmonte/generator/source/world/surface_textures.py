"""Neutral linear texture detail shared by the valley and island materials."""
import numpy as np
from PIL import Image


def neutral_detail(image):
    srgb = np.asarray(image.convert('RGB'), float) / 255.
    linear = np.where(srgb <= .04045, srgb / 12.92, ((srgb + .055) / 1.055) ** 2.4)
    neutral = np.clip(linear / np.maximum(linear.mean((0, 1)), .001) / 2., 0, 1)
    encoded = np.where(neutral <= .0031308, neutral * 12.92, 1.055 * neutral ** (1 / 2.4) - .055)
    return Image.fromarray(np.uint8(np.clip(encoded * 255, 0, 255)))
