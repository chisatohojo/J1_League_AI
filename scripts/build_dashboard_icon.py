"""Explicit developer-only rasterization of our font-free SVG (Pillow required).

No downloaded assets. SVG rect/polygon geometry is the single editable source.
Never runs at launcher/install time.
"""
from pathlib import Path
import xml.etree.ElementTree as ET


def build(root: Path):
    from PIL import Image, ImageDraw
    svg = ET.parse(root / 'web/assets/j1ai.svg').getroot()
    scale = 4
    image = Image.new('RGBA', (256 * scale, 256 * scale))
    draw = ImageDraw.Draw(image)
    for child in svg:
        tag = child.tag.split('}')[-1]
        if tag == 'rect':
            draw.rounded_rectangle((0, 0, 256 * scale - 1, 256 * scale - 1),
                                   radius=int(child.attrib['rx']) * scale, fill=child.attrib['fill'])
        elif tag == 'polygon':
            points = [tuple(int(n) * scale for n in p.split(',')) for p in child.attrib['points'].split()]
            draw.polygon(points, fill=child.attrib['fill'])
        else:
            raise ValueError('Unreviewed SVG shape')
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    image.save(root / 'web/assets/j1ai.ico', sizes=[(n, n) for n in [16, 24, 32, 48, 64, 128, 256]])


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
