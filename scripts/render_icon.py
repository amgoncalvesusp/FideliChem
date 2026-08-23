"""Render the FideliChem vector mark as a multi-resolution Windows ICO."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def render(size: int) -> Image.Image:
    scale = 4
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def point(value: float) -> int:
        return round(value * scale)

    margin = point(size * 0.06)
    radius = point(size * 0.2)
    draw.rounded_rectangle(
        (margin, margin, canvas_size - margin, canvas_size - margin),
        radius=radius,
        fill="#0B1220",
        outline="#385170",
        width=max(point(size * 0.012), 1),
    )
    inset = point(size * 0.11)
    draw.rounded_rectangle(
        (inset, inset, canvas_size - inset, canvas_size - inset),
        radius=point(size * 0.15),
        fill="#111B2F",
    )

    center = (point(size * 0.5), point(size * 0.5))
    orbit_box = (
        point(size * 0.22),
        point(size * 0.2),
        point(size * 0.78),
        point(size * 0.8),
    )
    orbit_color = "#385170"
    orbit_width = max(point(size * 0.022), 1)
    draw.ellipse(orbit_box, outline=orbit_color, width=orbit_width)
    # Two rotated ellipses approximate the same molecular orbital composition
    # as the canonical SVG at small raster sizes.
    draw.arc(orbit_box, 35, 215, fill="#5BE6C7", width=orbit_width)
    draw.arc(orbit_box, 215, 395, fill="#385170", width=orbit_width)

    core_radius = point(size * 0.19)
    draw.ellipse(
        (
            center[0] - core_radius,
            center[1] - core_radius,
            center[0] + core_radius,
            center[1] + core_radius,
        ),
        fill="#5BE6C7",
        outline="#EAF2FF",
        width=max(point(size * 0.012), 1),
    )
    check = [
        (point(size * 0.40), point(size * 0.51)),
        (point(size * 0.47), point(size * 0.58)),
        (point(size * 0.61), point(size * 0.40)),
    ]
    draw.line(check, fill="#0B1220", width=max(point(size * 0.045), 1), joint="curve")

    node_radius = point(size * 0.045)
    for x, y in ((0.25, 0.34), (0.75, 0.34), (0.5, 0.78)):
        px, py = point(size * x), point(size * y)
        draw.ellipse(
            (px - node_radius, py - node_radius, px + node_radius, py + node_radius),
            fill="#5BE6C7",
            outline="#EAF2FF",
            width=max(point(size * 0.009), 1),
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    target = (
        Path(__file__).resolve().parents[1]
        / "src/fidelichem/gui/assets/fidelichem-mark.ico"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    images = [render(size) for size in (16, 24, 32, 48, 64, 128, 256)]
    images[0].save(target, format="ICO", sizes=[image.size for image in images])
    images[-1].save(target.with_suffix(".png"), format="PNG")


if __name__ == "__main__":
    main()
