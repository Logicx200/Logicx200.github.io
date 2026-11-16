"""Generate the built-in sample artwork for ASCII Studio.

Run from the project root:
    python tools/make_samples.py
"""

from __future__ import annotations

import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")
THUMBS = os.path.join(SAMPLES, "thumbs")
ASSETS = os.path.join(ROOT, "assets")
RNG = np.random.default_rng(20261117)
random.seed(20261117)


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def vertical_gradient(width: int, height: int, stops: list[tuple[float, str]]) -> np.ndarray:
    colors = np.array([hex_rgb(c) for _, c in stops], dtype=np.float64)
    positions = np.array([p for p, _ in stops], dtype=np.float64)
    ys = np.linspace(0.0, 1.0, height)
    rows = np.zeros((height, 3), dtype=np.float64)
    for channel in range(3):
        rows[:, channel] = np.interp(ys, positions, colors[:, channel])
    return np.repeat(rows[:, None, :], width, axis=1)


def add_radial_glow(
    image: np.ndarray,
    cx: float,
    cy: float,
    radius: float,
    color: str,
    strength: float = 1.0,
    falloff: float = 2.2,
) -> None:
    height, width = image.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max(radius, 1.0)
    glow = np.exp(-(dist**2) * falloff) * strength
    rgb = np.array(hex_rgb(color), dtype=np.float64)
    image += glow[..., None] * rgb * (1.0 / 255.0)


def screen_blend(image: np.ndarray, layer: np.ndarray, strength: float = 1.0) -> None:
    base = np.clip(image, 0, 255) / 255.0
    top = np.clip(layer, 0, 255) / 255.0
    result = 1.0 - (1.0 - base) * (1.0 - top * strength)
    image[:] = np.clip(result, 0.0, 1.0) * 255.0


def add_stars(
    image: np.ndarray,
    count: int,
    region_top: float = 0.0,
    region_bottom: float = 0.65,
    max_radius: float = 1.8,
    warm: bool = False,
) -> None:
    height, width = image.shape[:2]
    for _ in range(count):
        x = int(RNG.uniform(0, width))
        y = int(RNG.uniform(region_top * height, region_bottom * height))
        radius = RNG.uniform(0.35, max_radius)
        brightness = RNG.uniform(90, 245)
        if warm:
            color = (brightness, brightness * RNG.uniform(0.76, 0.9), brightness * RNG.uniform(0.55, 0.72))
        else:
            color = (brightness * RNG.uniform(0.72, 0.9), brightness * RNG.uniform(0.84, 0.98), brightness)
        stamp = Image.new("RGBA", (int(radius * 8 + 5), int(radius * 8 + 5)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(stamp)
        cx, cy = stamp.width / 2, stamp.height / 2
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=(int(color[0]), int(color[1]), int(color[2]), 235),
        )
        blur = stamp.filter(ImageFilter.GaussianBlur(radius * 0.9))
        left = int(x - blur.width / 2)
        top = int(y - blur.height / 2)
        _paste_rgba(image, blur, left, top)


def _paste_rgba(image: np.ndarray, overlay: Image.Image, left: int, top: int) -> None:
    height, width = image.shape[:2]
    alpha = np.array(overlay.getchannel("A"), dtype=np.float64) / 255.0
    rgb = np.array(overlay.convert("RGB"), dtype=np.float64)
    sx0 = max(0, left)
    sy0 = max(0, top)
    sx1 = min(width, left + overlay.width)
    sy1 = min(height, top + overlay.height)
    if sx0 >= sx1 or sy0 >= sy1:
        return
    ox0 = sx0 - left
    oy0 = sy0 - top
    ox1 = ox0 + (sx1 - sx0)
    oy1 = oy0 + (sy1 - sy0)
    a = alpha[oy0:oy1, ox0:ox1, None]
    image[sy0:sy1, sx0:sx1, :] = (
        rgb[oy0:oy1, ox0:ox1, :] * a + image[sy0:sy1, sx0:sx1, :] * (1.0 - a)
    )


def paste_pil(image: np.ndarray, layer: Image.Image, left: int, top: int) -> None:
    _paste_rgba(image, layer, left, top)


def add_grain(image: np.ndarray, amount: float = 3.0, warm_bias: float = 0.0) -> None:
    noise = RNG.normal(0.0, amount, image.shape)
    noise[..., 0] += warm_bias
    image += noise


def vignette(image: np.ndarray, strength: float = 0.22, softness: float = 1.55) -> None:
    height, width = image.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    nx = (xx - width / 2) / (width / 2)
    ny = (yy - height / 2) / (height / 2)
    dist = np.sqrt(nx * nx + ny * ny) / math.sqrt(2)
    mask = np.clip(1.0 - strength * (dist**softness), 0.0, 1.0)
    image *= mask[..., None]


def ridge_curve(width: int, base: float, amp: float, frequency: float, phase: float) -> np.ndarray:
    x = np.linspace(0, 1, width)
    return (
        base
        + amp * np.sin(x * math.pi * 2 * frequency + phase)
        + amp * 0.36 * np.sin(x * math.pi * 2 * (frequency * 2.7) + phase * 1.8)
        + amp * 0.16 * np.sin(x * math.pi * 2 * (frequency * 5.1) + phase * 0.5)
    )


def draw_ridge(
    image: np.ndarray,
    base_ratio: float,
    amp_ratio: float,
    frequency: float,
    phase: float,
    color: str,
    rim: str | None = None,
    rim_width: int = 2,
) -> None:
    height, width = image.shape[:2]
    curve = ridge_curve(width, base_ratio * height, amp_ratio * height, frequency, phase)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    points = [(x, int(curve[x])) for x in range(width)] + [(width, height), (0, height)]
    draw.polygon(points, fill=hex_rgb(color) + (255,))
    if rim:
        draw.line([(x, int(curve[x])) for x in range(width)], fill=hex_rgb(rim) + (120,), width=rim_width)
    blur = layer.filter(ImageFilter.GaussianBlur(0.4))
    paste_pil(image, blur, 0, 0)


def make_dunes() -> Image.Image:
    width, height = 1600, 1000
    image = vertical_gradient(
        width,
        height,
        [
            (0.0, "#050a17"),
            (0.26, "#101b33"),
            (0.48, "#3b3b56"),
            (0.64, "#94695c"),
            (0.76, "#e5a06b"),
            (0.84, "#f6c68c"),
            (1.0, "#241a1b"),
        ],
    )

    # layered warm clouds near the horizon
    cloud_layer = np.zeros_like(image)
    yy, xx = np.mgrid[0:height, 0:width]
    for cy, rx, ry, tint, strength in [
        (520, 850, 38, "#6d5664", 0.55),
        (558, 1050, 26, "#a87972", 0.55),
        (595, 900, 20, "#de9d79", 0.5),
        (465, 600, 20, "#544b64", 0.45),
    ]:
        mask = np.exp(-(((xx - width * 0.52) / rx) ** 2 + ((yy - cy) / ry) ** 2) * 2.2)
        cloud_layer += mask[..., None] * np.array(hex_rgb(tint), dtype=np.float64) * strength
    screen_blend(image, cloud_layer, 0.55)

    add_radial_glow(image, width * 0.71, height * 0.43, 430, "#ffd28c", strength=0.72, falloff=2.0)
    add_radial_glow(image, width * 0.71, height * 0.43, 130, "#ffe6b0", strength=0.75, falloff=1.3)
    add_radial_glow(image, width * 0.34, height * 0.72, 390, "#ff8b58", strength=0.16, falloff=2.8)

    add_stars(image, 260, region_top=0.0, region_bottom=0.46, max_radius=1.35, warm=False)

    # sun
    sun = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sun)
    sx, sy, sr = width * 0.71, height * 0.43, 77
    for i in range(14, 0, -1):
        radius = sr + i * 8
        alpha = int(5 + (14 - i) * 3.1)
        draw.ellipse([sx - radius, sy - radius, sx + radius, sy + radius], fill=(255, 210, 140, alpha))
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 236, 182, 255))
    paste_pil(image, sun.filter(ImageFilter.GaussianBlur(1.2)), 0, 0)

    # distant ridge silhouettes
    draw_ridge(image, 0.565, 0.030, 1.1, 1.3, "#493a49", rim="#8d6a66", rim_width=2)
    draw_ridge(image, 0.625, 0.048, 1.7, 3.9, "#332a37", rim="#7b5856", rim_width=2)
    draw_ridge(image, 0.695, 0.062, 1.25, 0.8, "#241e2a", rim="#704b48", rim_width=2)

    # foreground dunes
    draw_ridge(image, 0.775, 0.085, 0.9, 2.4, "#181318")
    draw_ridge(image, 0.858, 0.060, 1.45, 5.0, "#0d0c0e")
    draw_ridge(image, 0.945, 0.050, 1.8, 2.0, "#070707")

    # warm rim light on the nearest dune
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    curve = ridge_curve(width, 0.775 * height, 0.085 * height, 0.9, 2.4)
    points = [(x, int(curve[x]) + 3) for x in range(width)]
    draw.line(points, fill=(255, 165, 110, 85), width=3)
    paste_pil(image, layer.filter(ImageFilter.GaussianBlur(2.2)), 0, 0)

    # birds
    bird_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bird_layer)
    for bx, by, scale in [(920, 336, 0.9), (977, 312, 0.6), (1030, 352, 0.45)]:
        draw.arc(
            [bx - 14 * scale, by - 6 * scale, bx, by + 8 * scale],
            205,
            330,
            fill=(18, 16, 20, 225),
            width=max(1, int(2 * scale)),
        )
        draw.arc(
            [bx, by - 7 * scale, bx + 15 * scale, by + 7 * scale],
            210,
            335,
            fill=(18, 16, 20, 225),
            width=max(1, int(2 * scale)),
        )
    paste_pil(image, bird_layer, 0, 0)

    # filmic finishing
    add_grain(image, 4.2, warm_bias=0.6)
    vignette(image, 0.28, 1.35)
    image = np.clip(image, 0, 255).astype(np.uint8)
    result = Image.fromarray(image, "RGB")
    return result.filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=3))


def make_orb() -> Image.Image:
    width, height = 1400, 1050
    image = vertical_gradient(
        width,
        height,
        [
            (0.0, "#03090d"),
            (0.34, "#071a21"),
            (0.62, "#0b2a31"),
            (0.82, "#173a3d"),
            (1.0, "#06090b"),
        ],
    )

    # nebula wash
    add_radial_glow(image, width * 0.52, height * 0.46, 570, "#1d7b83", strength=0.24, falloff=2.4)
    add_radial_glow(image, width * 0.22, height * 0.28, 420, "#2b507b", strength=0.12, falloff=2.9)
    add_radial_glow(image, width * 0.81, height * 0.77, 360, "#7c4c55", strength=0.085, falloff=2.7)
    add_stars(image, 360, region_top=0.03, region_bottom=0.72, max_radius=1.5, warm=False)
    add_stars(image, 38, region_top=0.1, region_bottom=0.52, max_radius=2.2, warm=True)

    orb_cx = width * 0.52
    orb_cy = height * 0.44
    orb_r = 288

    # halo
    halo = np.zeros_like(image)
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.sqrt((xx - orb_cx) ** 2 + (yy - orb_cy) ** 2) / orb_r
    halo_mask = np.exp(-((np.maximum(dist - 1.0, 0)) * 4.2) ** 1.4)
    halo_mask *= dist > 0.92
    halo += halo_mask[..., None] * np.array(hex_rgb("#54dbe3"), dtype=np.float64) * 0.5
    screen_blend(image, halo, 1.0)

    # sphere layers
    orb_layer = np.zeros((height, width, 4), dtype=np.float64)
    dx = (xx - orb_cx) / orb_r
    dy = (yy - orb_cy) / orb_r
    rr = dx * dx + dy * dy
    inside = rr <= 1.0
    zz = np.sqrt(np.maximum(0.0, 1.0 - rr))
    nz = np.clip(zz, 0.0, 1.0)

    light = np.array([-0.52, -0.64, 0.72])
    light = light / np.linalg.norm(light)
    diffuse = np.clip(dx * light[0] + dy * light[1] + nz * light[2], 0.0, 1.0)
    rim = np.power(np.clip(rr, 0.0, 1.0), 7.0)
    bands = 0.55 + 0.45 * np.sin(dy * 9.5 + nz * 4.0 + 0.6)
    bands = np.clip(bands, 0.0, 1.0)
    spec = np.power(np.clip(dx * -0.34 + dy * -0.4 + nz * 0.85, 0.0, 1.0), 28.0)

    base = np.array(hex_rgb("#1b90a3"), dtype=np.float64)
    deep = np.array(hex_rgb("#06323f"), dtype=np.float64)
    crest = np.array(hex_rgb("#b7fff2"), dtype=np.float64)
    color = (
        deep[None, None, :]
        + (base - deep)[None, None, :] * (0.2 + diffuse[..., None] * 0.9)
        + (crest - base)[None, None, :] * (spec[..., None] * 0.65 + rim[..., None] * 0.2)
    )
    color *= (0.72 + bands[..., None] * 0.34)
    # subtle atmospheric limb darkening
    color *= (0.82 + nz[..., None] * 0.32)
    alpha = inside.astype(np.float64)
    # soften sphere edge
    edge = np.clip((1.0 - rr) * 160.0, 0.0, 1.0)
    alpha = np.minimum(alpha, edge)
    orb_layer[..., :3] = np.clip(color, 0, 255)
    orb_layer[..., 3] = alpha * 255.0
    orb_image = Image.fromarray(np.clip(np.nan_to_num(orb_layer), 0, 255).astype(np.uint8), "RGBA")

    # ring behind the orb
    ring_layer = np.zeros((height, width, 4), dtype=np.float64)
    tilt = math.radians(-17)
    cos_t = math.cos(tilt)
    sin_t = math.sin(tilt)
    u = xx * cos_t + yy * sin_t
    v = -xx * sin_t + yy * cos_t
    ex = (u - (orb_cx * cos_t + orb_cy * sin_t)) / (orb_r * 1.72)
    ey = (v - (-orb_cx * sin_t + orb_cy * cos_t)) / (orb_r * 0.34)
    ellipse = np.sqrt(ex * ex + ey * ey)
    ring_mask = np.exp(-(((ellipse - 1.0) / 0.022) ** 2))
    ring_mask *= 0.9
    ring_color = np.array(hex_rgb("#a9fbff"), dtype=np.float64)
    ring_layer[..., :3] = ring_color * 0.82
    ring_layer[..., 3] = np.clip(ring_mask, 0, 1) * 235
    ring_image = Image.fromarray(np.clip(ring_layer, 0, 255).astype(np.uint8), "RGBA")
    paste_pil(image, ring_image.filter(ImageFilter.GaussianBlur(0.45)), 0, 0)

    # orb
    paste_pil(image, orb_image.filter(ImageFilter.GaussianBlur(0.55)), 0, 0)

    # foreground horizon / dunes
    draw_ridge(image, 0.827, 0.026, 1.15, 3.2, "#061012")
    draw_ridge(image, 0.884, 0.035, 0.8, 5.4, "#040a0b")
    draw_ridge(image, 0.952, 0.030, 1.6, 1.6, "#020405")

    # distant ridge reflection of ring glow
    add_radial_glow(image, orb_cx, height * 0.87, 260, "#3ad1ce", strength=0.075, falloff=2.1)

    # tiny observer
    observer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(observer)
    bx = width * 0.205
    by = height * 0.884
    scale = 0.48
    head_r = 10 * scale
    draw.ellipse(
        [bx - head_r, by - 72 * scale - head_r, bx + head_r, by - 72 * scale + head_r],
        fill=(2, 4, 5, 255),
    )
    draw.polygon(
        [
            (bx - 12 * scale, by - 62 * scale),
            (bx + 10 * scale, by - 62 * scale),
            (bx + 13 * scale, by - 25 * scale),
            (bx + 4 * scale, by - 14 * scale),
            (bx + 12 * scale, by + 2 * scale),
            (bx + 3 * scale, by),
            (bx - 4 * scale, by - 15 * scale),
            (bx - 12 * scale, by + 2 * scale),
            (bx - 17 * scale, by - 2 * scale),
            (bx - 7 * scale, by - 16 * scale),
            (bx - 16 * scale, by - 26 * scale),
        ],
        fill=(2, 4, 5, 255),
    )
    # staff
    draw.line(
        [(bx + 24 * scale, by - 52 * scale), (bx + 31 * scale, by + 3 * scale)],
        fill=(2, 4, 5, 255),
        width=max(1, int(3 * scale)),
    )
    paste_pil(image, observer, 0, 0)

    add_grain(image, 3.8, warm_bias=0.25)
    vignette(image, 0.3, 1.35)
    image = np.clip(image, 0, 255).astype(np.uint8)
    result = Image.fromarray(image, "RGB")
    return result.filter(ImageFilter.UnsharpMask(radius=1.15, percent=60, threshold=3))


def make_grain_asset() -> None:
    rng = np.random.default_rng(7)
    size = 128
    noise = np.clip(rng.normal(128, 46, (size, size, 3)), 0, 255).astype(np.uint8)
    alpha = rng.integers(18, 80, (size, size), dtype=np.uint8)
    rgba = np.dstack([noise, alpha])
    Image.fromarray(rgba, "RGBA").save(os.path.join(ASSETS, "grain.png"), optimize=True)


def save_sample(image: Image.Image, name: str, thumb_center=(0.5, 0.5)) -> None:
    path = os.path.join(SAMPLES, name)
    image.save(path, "JPEG", quality=90, optimize=True, progressive=True)
    thumb = ImageOps.fit(
        image,
        (480, 270),
        method=Image.Resampling.LANCZOS,
        centering=thumb_center,
    )
    thumb.save(os.path.join(THUMBS, name), "JPEG", quality=86, optimize=True, progressive=True)
    print("wrote", path, os.path.getsize(path), "bytes")


def main() -> None:
    os.makedirs(SAMPLES, exist_ok=True)
    os.makedirs(THUMBS, exist_ok=True)
    os.makedirs(ASSETS, exist_ok=True)
    save_sample(make_dunes(), "dusk-dunes.jpg", thumb_center=(0.53, 0.46))
    save_sample(make_orb(), "floating-orb.jpg", thumb_center=(0.5, 0.46))
    make_grain_asset()
    print("wrote", os.path.join(ASSETS, "grain.png"))


if __name__ == "__main__":
    main()
