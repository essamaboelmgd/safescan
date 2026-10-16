"""One deterministic preprocessing contract for import, training and inference."""
from dataclasses import dataclass
from io import BytesIO
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

FEATURE_VERSION = 'hsv128-edge64-v1'
FEATURE_DIM = 192


@dataclass
class ProcessedImage:
    rgb: np.ndarray
    features: np.ndarray
    phash: str
    warnings: list[str]


def preprocess(data: bytes, max_pixels: int = 12_000_000) -> ProcessedImage:
    if not data:
        raise ValueError('Image is empty.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Only JPEG, PNG and WebP images are supported.')
                width, height = source.size
                if width * height > max_pixels:
                    raise ValueError('Image exceeds the pixel limit.')
                if min(width, height) < 32:
                    raise ValueError('Image must be at least 32 by 32 pixels.')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Animated images are not supported.')
                image = ImageOps.exif_transpose(source).convert('RGB')
                # Preserve aspect ratio, pad with a neutral background.
                image = ImageOps.pad(image, (224, 224), color=(127, 127, 127))
                rgb = np.array(image)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Invalid or unsafe image data.') from exc

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(denoised, 60, 150)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).flatten()
    hist /= max(float(hist.sum()), 1.0)
    edge_grid = cv2.resize(edges, (8, 8), interpolation=cv2.INTER_AREA).flatten() / 255.0
    features = np.concatenate([hist, edge_grid]).astype(np.float32)
    features /= max(float(np.linalg.norm(features)), 1e-12)
    dct = cv2.dct(cv2.resize(gray, (32, 32)).astype(np.float32))[:8, :8].flatten()
    bits = dct > np.median(dct[1:])
    bits[0] = False
    phash = f'{int("".join("1" if bit else "0" for bit in bits), 2):016x}'
    quality = []
    if cv2.Laplacian(gray, cv2.CV_64F).var() < 35:
        quality.append('Image has little detail or blur; use a sharp close-up of the label.')
    if gray.mean() < 35 or gray.mean() > 225:
        quality.append('Lighting may hide packaging details.')
    return ProcessedImage(rgb, features, phash, quality)


def canonical_png(image: ProcessedImage) -> bytes:
    output = BytesIO()
    Image.fromarray(image.rgb).save(output, format='PNG')
    return output.getvalue()
