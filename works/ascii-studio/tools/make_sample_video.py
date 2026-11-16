"""Render the built-in sample video for ASCII Studio.

Produces samples/orbital-drift.webm plus a thumbnail.
Requires numpy + OpenCV (already available in the development environment).

Run from the project root:
    python tools/make_sample_video.py
"""

from __future__ import annotations

import math
import os
import cv2
import numpy as np
from PIL import Image


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")
THUMBS = os.path.join(SAMPLES, "thumbs")

WIDTH = 960
HEIGHT = 540
FPS = 24
SECONDS = 6
FRAMES = FPS * SECONDS
RNG = np.random.default_rng(1127)


def hex_rgb(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array([int(value[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def smoothstep(x: np.ndarray | float) -> np.ndarray | float:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def vertical_gradient(width: int, height: int, stops: list[tuple[float, str]]) -> np.ndarray:
    colors = np.array([hex_rgb(c) for _, c in stops], dtype=np.float32)
    positions = np.array([p for p, _ in stops], dtype=np.float32)
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)
    rows = np.zeros((height, 3), dtype=np.float32)
    for channel in range(3):
        rows[:, channel] = np.interp(ys, positions, colors[:, channel])
    return np.repeat(rows[:, None, :], width, axis=1)


def blend_patch(frame: np.ndarray, patch: np.ndarray, x0: int, y0: int, alpha: np.ndarray) -> None:
    height, width = frame.shape[:2]
    py, px = patch.shape[:2]
    x1 = min(width, x0 + px)
    y1 = min(height, y0 + py)
    if x1 <= x0 or y1 <= y0:
        return
    a = np.clip(alpha[: y1 - y0, : x1 - x0], 0.0, 1.0)[..., None]
    region = frame[y0:y1, x0:x1, :]
    frame[y0:y1, x0:x1, :] = region * (1.0 - a) + patch[: y1 - y0, : x1 - x0, :] * a


def build_stars() -> tuple[np.ndarray, np.ndarray]:
    """Return a static star layer and a second twinkling star layer."""
    base = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
    twinkle = np.zeros_like(base)
    for i in range(280):
        x = int(RNG.uniform(0, WIDTH))
        y = int(RNG.uniform(0, HEIGHT * 0.72))
        if y > HEIGHT * 0.5 and RNG.random() < 0.45:
            continue
        brightness = RNG.uniform(25, 120)
        color = np.array(
            [
                brightness * RNG.uniform(0.75, 0.95),
                brightness * RNG.uniform(0.82, 0.98),
                brightness,
            ],
            dtype=np.float32,
        )
        radius = RNG.uniform(0.3, 1.25)
        target = twinkle if i % 7 == 0 else base
        cv2.circle(target, (x, y), max(1, int(round(radius))), color.tolist(), -1, cv2.LINE_AA)
    base = cv2.GaussianBlur(base, (0, 0), 0.55)
    for i in range(22):
        x = int(RNG.uniform(0, WIDTH))
        y = int(RNG.uniform(0, HEIGHT * 0.6))
        color = [RNG.uniform(90, 160), RNG.uniform(95, 155), RNG.uniform(75, 120)]
        cv2.circle(base, (x, y), 1, color, -1, cv2.LINE_AA)
    return base, twinkle


def build_foreground() -> tuple[np.ndarray, np.ndarray]:
    """Pre-render the dune silhouettes and the tiny observer."""
    layer = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
    alpha = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    xs = np.arange(WIDTH, dtype=np.float32) / WIDTH
    yy = np.arange(HEIGHT, dtype=np.float32)[:, None]
    xx = np.arange(WIDTH, dtype=np.float32)[None, :]

    ridges = [
        (0.815, 0.020, 1.10, 3.2, hex_rgb("#071216")),
        (0.872, 0.029, 0.82, 5.4, hex_rgb("#040c0e")),
        (0.940, 0.026, 1.62, 1.6, hex_rgb("#020506")),
    ]
    for base, amp, freq, phase, color in ridges:
        curve = (
            base * HEIGHT
            + amp * HEIGHT * np.sin(xs * math.pi * 2 * freq + phase)
            + amp * HEIGHT * 0.36 * np.sin(xs * math.pi * 2 * freq * 2.7 + phase * 1.8)
            + amp * HEIGHT * 0.16 * np.sin(xs * math.pi * 2 * freq * 5.1 + phase * 0.5)
        )
        mask = (yy >= curve[None, :]).astype(np.float32)
        layer = layer * (1.0 - mask[..., None]) + color[None, None, :] * mask[..., None]
        alpha = np.maximum(alpha, mask * 0.98)

        rim = np.exp(-((yy - curve[None, :] - 1.5) ** 2) / 2.0) * 0.24
        layer += rim[..., None] * np.array([54, 116, 115], dtype=np.float32)

    # observer silhouette
    obs = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    bx = int(WIDTH * 0.195)
    by = int(HEIGHT * 0.872)
    scale = 0.48
    head_r = int(9 * scale)
    cv2.circle(obs, (bx, by - int(73 * scale)), head_r, 1.0, -1, cv2.LINE_AA)
    body = np.array(
        [
            (bx - int(12 * scale), by - int(62 * scale)),
            (bx + int(10 * scale), by - int(62 * scale)),
            (bx + int(13 * scale), by - int(24 * scale)),
            (bx + int(5 * scale), by - int(13 * scale)),
            (bx + int(12 * scale), by + int(2 * scale)),
            (bx + int(3 * scale), by + int(2 * scale)),
            (bx - int(4 * scale), by - int(14 * scale)),
            (bx - int(12 * scale), by + int(3 * scale)),
            (bx - int(18 * scale), by - int(2 * scale)),
            (bx - int(7 * scale), by - int(16 * scale)),
            (bx - int(16 * scale), by - int(26 * scale)),
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(obs, [body], 1.0, cv2.LINE_AA)
    cv2.line(
        obs,
        (bx + int(24 * scale), by - int(52 * scale)),
        (bx + int(31 * scale), by + int(3 * scale)),
        1.0,
        max(1, int(2 * scale)),
        cv2.LINE_AA,
    )
    layer = layer * (1.0 - obs[..., None]) + np.array([1, 3, 4], dtype=np.float32)[None, None, :] * obs[..., None]
    alpha = np.maximum(alpha, obs * 0.99)
    return layer, alpha


def render_orb(frame: np.ndarray, cx: float, cy: float, radius: float, t: float) -> None:
    pad = int(radius * 2.25)
    x0 = max(0, int(cx) - pad)
    x1 = min(WIDTH, int(cx) + pad)
    y0 = max(0, int(cy) - pad)
    y1 = min(HEIGHT, int(cy) + pad)
    if x1 <= x0 or y1 <= y0:
        return

    xs = np.arange(x0, x1, dtype=np.float32)
    ys = np.arange(y0, y1, dtype=np.float32)
    nx = (xs[None, :] - cx) / radius
    ny = (ys[:, None] - cy) / radius
    rr = nx * nx + ny * ny

    patch = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.float32)
    alpha = np.zeros((y1 - y0, x1 - x0), dtype=np.float32)

    # soft halo
    dist = np.sqrt((xs[None, :] - cx) ** 2 + (ys[:, None] - cy) ** 2) / radius
    halo = np.exp(-(np.maximum(dist - 1.0, 0.0) * 4.8) ** 1.35) * 0.55
    halo *= smoothstep(dist - 0.95)
    patch += halo[..., None] * hex_rgb("#2cbfc6")[None, None, :] * 0.55
    alpha = np.maximum(alpha, halo)

    # back portion of the ring
    tilt = math.radians(-17)
    cos_t = math.cos(tilt)
    sin_t = math.sin(tilt)
    gx = xs[None, :] - cx
    gy = ys[:, None] - cy
    u = gx * cos_t + gy * sin_t
    v = -gx * sin_t + gy * cos_t
    ellipse = np.sqrt((u / (radius * 1.72)) ** 2 + (v / (radius * 0.335)) ** 2)
    ring = np.exp(-(((ellipse - 1.0) / 0.023) ** 2)) * 0.9
    ring *= smoothstep(dist - 1.01)
    patch = patch * (1.0 - ring[..., None]) + hex_rgb("#9ef7ff")[None, None, :] * ring[..., None]
    alpha = np.maximum(alpha, ring)

    # sphere
    inside = rr <= 1.0
    z = np.sqrt(np.maximum(0.0, 1.0 - rr))
    light = np.array([-0.52, -0.66, 0.72], dtype=np.float32)
    light /= np.linalg.norm(light)
    diffuse = np.clip(nx * light[0] + ny * light[1] + z * light[2], 0.0, 1.0)
    rim = np.power(np.clip(rr, 0.0, 1.0), 7.0)
    bands = np.clip(0.58 + 0.42 * np.sin(ny * 10.5 + z * 4.2 + 0.8 + t * 0.18), 0.0, 1.0)
    swirl = np.sin(np.arctan2(ny, nx) * 4.0 + z * 12.0 - t * 0.55) * 0.06
    spec = np.power(np.clip(nx * -0.34 + ny * -0.4 + z * 0.85, 0.0, 1.0), 30.0)

    deep = hex_rgb("#052d38")
    base = hex_rgb("#1a93a5")
    crest = hex_rgb("#bafff2")
    color = (
        deep[None, None, :]
        + (base - deep)[None, None, :] * (0.18 + diffuse[..., None] * 0.88)
        + (crest - base)[None, None, :] * (spec[..., None] * 0.65 + rim[..., None] * 0.22)
    )
    color *= 0.7 + bands[..., None] * 0.35 + swirl[..., None]
    color *= 0.8 + z[..., None] * 0.35
    edge_alpha = inside.astype(np.float32) * np.clip((1.0 - rr) * 180.0, 0.0, 1.0)

    patch = patch * (1.0 - edge_alpha[..., None]) + color * edge_alpha[..., None]
    alpha = np.maximum(alpha, edge_alpha)

    blend_patch(frame, patch, x0, y0, alpha)


def render_satellite(frame: np.ndarray, cx: float, cy: float, radius: float, t: float) -> None:
    for trail in range(18):
        angle = t * 0.75 - trail * 0.055
        sx = cx + math.cos(angle) * radius * 1.62
        sy = cy + math.sin(angle) * radius * 0.48 + math.sin(angle * 1.7) * radius * 0.05
        strength = max(0.0, 1.0 - trail / 18.0) ** 2
        color = (
            np.array([235, 255, 248], dtype=np.float32) * strength
        )
        overlay = np.zeros_like(frame)
        cv2.circle(overlay, (int(sx), int(sy)), 2 if trail == 0 else 1, color.tolist(), -1, cv2.LINE_AA)
        frame += overlay


def main() -> None:
    os.makedirs(SAMPLES, exist_ok=True)
    os.makedirs(THUMBS, exist_ok=True)

    sky = vertical_gradient(
        WIDTH,
        HEIGHT,
        [
            (0.0, "#02070a"),
            (0.32, "#06151b"),
            (0.62, "#0a2429"),
            (0.83, "#12363a"),
            (1.0, "#04090a"),
        ],
    )
    star_base, star_twinkle = build_stars()
    foreground, foreground_alpha = build_foreground()

    yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    nx = (xx - WIDTH / 2) / (WIDTH / 2)
    ny = (yy - HEIGHT / 2) / (HEIGHT / 2)
    vignette = np.clip(1.0 - 0.30 * (np.sqrt(nx * nx + ny * ny) / math.sqrt(2)) ** 1.35, 0.0, 1.0)
    vignette = vignette[..., None]
    grain = [RNG.normal(0, 1.7, (HEIGHT, WIDTH, 3)).astype(np.float32) for _ in range(4)]

    output_path = os.path.join(SAMPLES, "orbital-drift.webm")
    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*"VP80"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise SystemExit("OpenCV 无法启动 VP8 编码器，请检查视频编码支持。")

    thumb_frame = None
    for index in range(FRAMES):
        t = index / FPS
        frame = sky.copy()

        # breathing nebula glow
        glow = np.exp(-(((xx - WIDTH * 0.52) / (WIDTH * 0.36)) ** 2 + ((yy - HEIGHT * 0.44) / (HEIGHT * 0.48)) ** 2) * 2.2)
        frame += glow[..., None] * hex_rgb("#1f8d91")[None, None, :] * (0.075 + 0.02 * math.sin(t * 0.8))
        warm = np.exp(-(((xx - WIDTH * 0.82) / (WIDTH * 0.25)) ** 2 + ((yy - HEIGHT * 0.2) / (HEIGHT * 0.3)) ** 2) * 2.6)
        frame += warm[..., None] * hex_rgb("#8b4d53")[None, None, :] * 0.045

        frame += star_base
        frame += star_twinkle * (0.68 + 0.32 * math.sin(t * 1.9))

        cx = WIDTH * 0.52 + math.sin(t * 0.32) * 18
        cy = HEIGHT * 0.44 + math.cos(t * 0.28) * 9
        radius = 142 + math.sin(t * 0.45) * 5

        render_orb(frame, cx, cy, radius, t)
        render_satellite(frame, cx, cy, radius, t)

        # foreground
        frame = frame * (1.0 - foreground_alpha[..., None]) + foreground
        frame *= vignette

        # subtle animated aurora line behind the horizon
        aurora_y = HEIGHT * 0.79 + math.sin(t * 0.9) * 3
        aurora = np.exp(-((yy - aurora_y) / 13.0) ** 2) * (0.05 + 0.025 * math.sin(t * 1.3 + 1.1))
        frame += aurora[..., None] * hex_rgb("#3fd1c8")[None, None, :]

        frame += grain[index % len(grain)]
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        image = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        if index == int(FPS * 0.35):
            thumb_frame = image.copy()

        writer.write(image)

        if index % 24 == 0:
            print(f"[progress {index}/{FRAMES}] rendering sample video")

    writer.release()
    print(f"wrote {output_path} ({os.path.getsize(output_path)} bytes)")

    if thumb_frame is None:
        thumb_frame = image.copy()
    thumb = cv2.resize(thumb_frame, (480, 270), interpolation=cv2.INTER_AREA)
    thumb_rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
    thumb_path = os.path.join(THUMBS, "orbital-drift.jpg")
    Image.fromarray(thumb_rgb).save(thumb_path, "JPEG", quality=88, optimize=True)
    print(f"wrote {thumb_path}")


if __name__ == "__main__":
    main()
