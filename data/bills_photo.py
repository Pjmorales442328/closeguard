# data/bills_photo.py — makes a flat bill render look photographed: desk, shadow, perspective, uneven light, noise, JPEG.
import io

import numpy as np
from PIL import Image, ImageFilter


def _coeffs(dst, src):
    a, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    return np.linalg.solve(np.array(a, float), np.array(b, float))


def photo(paper: Image.Image, rng, strength=1.0, extra_rot=0.0, quality=78, blur=0.6) -> bytes:
    """paper: flat RGB render. strength scales perspective, light unevenness and noise. Returns JPEG bytes."""
    w, h = paper.size
    pad = 70
    cw, ch = w + 2 * pad, h + 2 * pad
    rgba = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    rgba.paste(paper.convert("RGBA"), (pad, pad))
    if extra_rot:
        rgba = rgba.rotate(extra_rot, resample=Image.BICUBIC, center=(cw / 2, ch / 2))
    j = 14 * strength
    src = [(0, 0), (cw, 0), (cw, ch), (0, ch)]
    dst = [(rng.uniform(-j, j) + x, rng.uniform(-j, j) + y) for x, y in src]
    warped = rgba.transform((cw, ch), Image.PERSPECTIVE, _coeffs(dst, src), Image.BICUBIC)
    desk = np.zeros((ch, cw, 3), float) + np.array([92, 80, 68])
    desk += rng.normal(0, 6, (ch, cw, 1))  # coarse wood-ish grain
    base = Image.fromarray(desk.clip(0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.2))
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow.putalpha(warped.getchannel("A").point(lambda a: int(a * 0.55)).filter(ImageFilter.GaussianBlur(9)))
    shifted = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shifted.paste(shadow, (8, 11))
    base = Image.alpha_composite(base.convert("RGBA"), shifted)
    img = np.asarray(Image.alpha_composite(base, warped).convert("RGB"), float)
    yy, xx = np.mgrid[0:ch, 0:cw]
    ang = rng.uniform(0, 6.28)
    light = 1 - 0.16 * strength * (np.cos(ang) * xx / cw + np.sin(ang) * yy / ch)  # uneven light
    light *= 1 - 0.22 * strength * (((xx - cw / 2) / cw) ** 2 + ((yy - ch / 2) / ch) ** 2)  # vignette
    img = img * light[..., None] + rng.normal(0, 3.5 * strength, img.shape)
    out = Image.fromarray(img.clip(0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(blur))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
