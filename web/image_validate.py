"""🛡️ REAL-IMAGE VALIDATOR — "NO IMAGE" / फ़र्ज़ी thumbnail कभी DB में न जाए।

`/warmup_thumbs` (और `/api/thumb` probe) Telegram से thumb bytes लाता है। सिर्फ़
`thumbs[0].file_id` मौजूद होना काफ़ी नहीं है: Telegram कभी-कभी generated
placeholder ("NO IMAGE" कार्ड), 1×1 pixel, सादा रंग का खाली frame या कोई error
body दे देता है। v5 (`plugins/warmup.py`) इसलिए bytes download करके `send_photo`
से दोबारा upload करता था — Telegram खुद सच्ची image ही accept करता है।

fsv1 इस guarantee को और आगे ले जाता है: upload से **पहले** bytes खुद validate
करता है (magic bytes / असली dimensions / न्यूनतम आकार / रंग-variance / placeholder
markers)। जो pass न हो उसे कभी `TG_ID:` में save नहीं करते — `NO_THUMB` mark कर
दिया जाता है, ताकि fake "no image" poster web पर कभी न दिखे।

Pillow `requirements.txt` में है, पर available न हो तो pure-Python fallback चलता
है (PNG/JPEG header parse + PNG IDAT variance) — validator कभी import error से
thumbnail flow नहीं रोकता।
"""

import io
import logging
import zlib

logger = logging.getLogger(__name__)

# Telegram thumbnail आमतौर पर ≥ 90px होती है; placeholder 1×1 / 16×16 होता है
DEFAULT_MIN_BYTES = 512
DEFAULT_MIN_DIM = 48
DEFAULT_MIN_STDDEV = 6.0

# कुछ bots placeholder image में ये literal strings डालते हैं (PNG tEXt chunk)
_PLACEHOLDER_MARKERS = (
    b"NO IMAGE", b"NO-IMAGE", b"NO_IMAGE", b"NO THUMB",
    b"NO THUMBNAIL", b"NO POSTER", b"NO_PREVIEW",
)

try:
    from PIL import Image, ImageStat
except Exception:                                    # pragma: no cover
    Image = ImageStat = None


def is_image_magic(data: bytes) -> bool:
    """JPEG / PNG / WEBP ही — SVG, HTML error page, JSON, GIF tracking pixel नहीं।"""
    if not data or len(data) < 12:
        return False
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )


def _png_dims(data):
    if len(data) >= 24 and data[12:16] == b"IHDR":
        return (int.from_bytes(data[16:20], "big"),
                int.from_bytes(data[20:24], "big"))
    return 0, 0


def _jpeg_dims(data):
    pos, end = 2, len(data)
    while pos + 9 < end:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        if length < 2:
            break
        # SOF0..SOF15 (C4/C8/CC = DHT/JPG/DAC नहीं)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return (int.from_bytes(data[pos + 7:pos + 9], "big"),
                    int.from_bytes(data[pos + 5:pos + 7], "big"))
        pos += 2 + length
    return 0, 0


def _webp_dims(data):
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        return (int.from_bytes(data[24:27], "little") + 1,
                int.from_bytes(data[27:30], "little") + 1)
    if chunk == b"VP8 " and len(data) >= 30:
        return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                int.from_bytes(data[28:30], "little") & 0x3FFF)
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    return 0, 0


def image_dimensions(data: bytes):
    """(w, h) — Pillow हो तो वहीं से, warna header parse (fail-soft)।"""
    if not is_image_magic(data):
        return 0, 0
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                return int(img.size[0]), int(img.size[1])
        except Exception:
            pass
    if data.startswith(b"\x89PNG"):
        return _png_dims(data)
    if data[:4] == b"RIFF":
        return _webp_dims(data)
    return _jpeg_dims(data)


def _png_pixel_stddev(data: bytes):
    """Pillow-न-होने पर PNG के pixels की **per-channel** stddev (pure Python)।

    ⚠️ सादे रंग की image में भी raw scanline bytes `0, r,g,b, r,g,b…` होते हैं,
    इसलिए पूरे buffer की byte-variance से blank placeholder पकड़ नहीं आता।
    Channel-wise variance लेने पर सादी image ≈ 0 और असली frame ≫ 0 मिलता है।
    """
    if not data.startswith(b"\x89PNG") or len(data) < 33:
        return None
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    depth, color = data[24], data[25]
    if depth != 8 or color not in (2, 6) or not (0 < w <= 8192 and 0 < h <= 8192):
        return None                       # palette/16-bit → Pillow पर छोड़ दो
    bpp = 3 if color == 2 else 4
    stride = w * bpp
    compressed, pos = bytearray(), 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        typ = data[pos + 4:pos + 8]
        if typ == b"IDAT":
            compressed.extend(data[pos + 8:pos + 8 + length])
        pos += 12 + length
        if typ == b"IEND":
            break
    try:
        raw = zlib.decompress(bytes(compressed))
    except Exception:
        return None
    # PNG filter types 0–4 undo करें, नहीं तो filtered delta bytes झूठी variance
    # दिखा सकते हैं। बड़ी image पर सिर्फ़ हर k-th row sample करते हैं (Pillow न हो
    # तो pure-Python loop भारी न पड़े)।
    step = max(1, (w * h) // 400_000)
    pixels, prev, pos = bytearray(), bytearray(stride), 0
    for y in range(h):
        if pos + 1 + stride > len(raw):
            break
        ft = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ft:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                if ft == 1:
                    pred = a
                elif ft == 2:
                    pred = b
                elif ft == 3:
                    pred = (a + b) // 2
                elif ft == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                else:
                    pred = 0
                line[i] = (line[i] + pred) & 255
        prev = line
        if y % step == 0:
            pixels.extend(line)
    if len(pixels) < bpp * 8:
        return 0.0
    best = 0.0
    for channel in range(bpp):
        vals = pixels[channel::bpp]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        best = max(best, var ** 0.5)
    return best


def _stddev(data: bytes):
    """RGB channel stddev — सादा/खाली placeholder ≈ 0, असली video frame ≫ 0।

    Pillow (`requirements.txt` में है) सब format decode करता है। न हो तो PNG
    pure-Python से check होता है; JPEG/WEBP में variance check skip होकर magic +
    dimensions + min-bytes + marker checks पर भरोसा रहता है।
    """
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                return max(ImageStat.Stat(img.convert("RGB")).stddev)
        except Exception:
            return None
    if data.startswith(b"\x89PNG"):
        return _png_pixel_stddev(data)
    return None


def validate_thumb(data, *, min_bytes=DEFAULT_MIN_BYTES,
                   min_dim=DEFAULT_MIN_DIM, min_stddev=DEFAULT_MIN_STDDEV):
    """`(ok, info)` — info में reason / width / height / stddev / bytes।

    `ok=False` ⇒ कभी DB में `TG_ID:` न लिखें, `NO_THUMB` mark करें।
    """
    info = {"bytes": len(data or b""), "width": 0, "height": 0, "stddev": 0.0, "reason": ""}
    if not data or len(data) < min_bytes:
        info["reason"] = "too-small-or-empty"
        return False, info
    if not is_image_magic(data):
        info["reason"] = "not-a-real-image"
        return False, info

    head = data[:8192].upper()
    if any(marker in head for marker in _PLACEHOLDER_MARKERS):
        info["reason"] = "placeholder-marker"
        return False, info

    # structure check: truncated / corrupt JPEG-PNG Pillow verify() यहाँ पकड़ता है
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.size[0] > 8192 or img.size[1] > 8192:
                    info["reason"] = "oversized"
                    return False, info
                img.verify()
        except Exception:
            info["reason"] = "corrupt-image"
            return False, info

    w, h = image_dimensions(data)
    info["width"], info["height"] = w, h
    if w < min_dim or h < min_dim or w > 8192 or h > 8192:
        info["reason"] = "tiny-or-invalid-dimensions"
        return False, info

    sd = _stddev(data)
    if sd is not None:
        info["stddev"] = round(float(sd), 2)
        if sd < min_stddev:
            info["reason"] = "blank-uniform-placeholder"
            return False, info

    info["reason"] = "ok"
    return True, info
