"""Generate Android launcher resources from the supplied bitmap using Pillow.

Equivalent to the raster output of a launcher-icon generator; no Flutter
dependencies or source artwork are changed. Run from any working directory.
"""
from pathlib import Path
import json

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'android' / 'app' / 'src' / 'main' / 'res'
DENSITIES = {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}


def generate():
    source = ROOT / 'assets' / 'branding' / 'meyar_icon.png'
    with Image.open(source) as original:
        original.load()
        if original.width != original.height or original.width < 432:
            raise ValueError('Supply a square PNG at least 432 pixels per side.')
        image = original.convert('RGBA')
    generated = []
    for density, scale in DENSITIES.items():
        directory = RES / f'mipmap-{density}'
        directory.mkdir(exist_ok=True)
        legacy_size = round(48 * scale)
        legacy_path = directory / 'ic_launcher.png'
        image.resize((legacy_size, legacy_size), Image.Resampling.LANCZOS).save(legacy_path)
        # The artwork includes its dark teal tile and keeps the mark inside the
        # adaptive-icon safe area, so use the full square as the foreground.
        layer_size = round(108 * scale)
        foreground = image.resize((layer_size, layer_size), Image.Resampling.LANCZOS)
        foreground_path = directory / 'ic_launcher_foreground.png'
        foreground.save(foreground_path)
        generated.extend([
            {'path': legacy_path.relative_to(ROOT).as_posix(), 'pixels': legacy_size},
            {'path': foreground_path.relative_to(ROOT).as_posix(), 'pixels': layer_size},
        ])
    adaptive = RES / 'mipmap-anydpi-v26'
    adaptive.mkdir(exist_ok=True)
    (adaptive / 'ic_launcher.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/safescan_launcher_background" />\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
        '</adaptive-icon>\n', encoding='utf-8',
    )
    (RES / 'values' / 'safescan_launcher.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<resources>\n'
        '    <string name="safescan_app_name">Meyar</string>\n'
        '    <color name="safescan_launcher_background">#143437</color>\n'
        '</resources>\n', encoding='utf-8',
    )
    print(json.dumps({'source': str(source), 'generated_pngs': generated}, indent=2))


if __name__ == '__main__':
    generate()
