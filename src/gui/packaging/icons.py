"""Export the shared, deliberately simple SVG artwork to native app icons."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


SOURCE = Path(__file__).resolve().parents[1] / "assets/app.svg"


def prepare_icons(destination: Path, source: Path = SOURCE) -> None:
    # Pillow is a build dependency only; native launchers do not render SVGs.
    from PIL import Image, ImageDraw

    document = ET.parse(source).getroot()
    if document.get("viewBox") != "0 0 256 256":
        raise ValueError("Application icon requires a 256-square viewBox")
    scale = 4
    image = Image.new("RGBA", (256 * scale, 256 * scale))
    draw = ImageDraw.Draw(image)
    for element in document:
        name = element.tag.rsplit("}", 1)[-1]
        if name == "title":
            continue
        if name == "rect":
            x, y, width, height, radius = [float(element.get(key, "0")) * scale for key in ("x", "y", "width", "height", "rx")]
            draw.rounded_rectangle((x, y, x + width, y + height), radius, fill=element.get("fill"))
        elif name == "polyline":
            if element.get("stroke-linecap") != "round" or element.get("stroke-linejoin") != "round":
                raise ValueError("Application icon polylines require round caps and joins")
            points = [tuple(float(value) * scale for value in point.split(",")) for point in element.get("points", "").split()]
            width = round(float(element.get("stroke-width", "1")) * scale)
            if len(points) < 2 or any(len(point) != 2 for point in points) or width <= 0:
                raise ValueError("Invalid application icon polyline")
            color = element.get("stroke")
            draw.line(points, fill=color, width=width, joint="curve")
            radius = width / 2
            for x, y in points:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        else:
            # This is an exporter for our artwork, not a general SVG renderer.
            raise ValueError(f"Unsupported application icon element: {name}")
    destination.mkdir(parents=True, exist_ok=True)
    image.save(destination / "app.png")
    image.save(destination / "app.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    image.save(destination / "app.icns")
