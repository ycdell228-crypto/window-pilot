"""Bound only the MCP image payload; retain the authoritative native PNG."""
from io import BytesIO
from pathlib import Path
import sys

from .win32 import PilotError

MAX_IMAGE_BYTES = 48_000  # Avoid DSH rc.2's large-image admission stack overflow.


def preview(data, native_size):
    if len(data) <= MAX_IMAGE_BYTES:
        return data, "image/png", native_size
    local = Path(__file__).resolve().parents[2] / ".local" / "wgc-deps"
    if local.is_dir() and str(local) not in sys.path:
        sys.path.insert(0, str(local))
    try:
        from PIL import Image
    except ImportError as exc:
        raise PilotError("IMAGE_DELIVERY_DEPENDENCY_MISSING: Pillow required for bounded preview; native capture retained") from exc
    with Image.open(BytesIO(data)) as source:
        if source.size != tuple(native_size):
            raise PilotError("IMAGE_DELIVERY_SIZE_MISMATCH")
        image = source.convert("RGB")
        max_width = min(image.width, 1280)
        while max_width >= 320:
            height = max(1, round(image.height * max_width / image.width))
            resized = image.resize((max_width, height), Image.Resampling.LANCZOS)
            for quality in (75, 55, 40, 25):
                out = BytesIO()
                resized.save(out, format="JPEG", quality=quality, optimize=True)
                encoded = out.getvalue()
                if len(encoded) <= MAX_IMAGE_BYTES:
                    return encoded, "image/jpeg", resized.size
            max_width = max_width * 3 // 4
    raise PilotError("IMAGE_DELIVERY_TOO_LARGE: cannot provide a bounded preview; no capture fallback")
