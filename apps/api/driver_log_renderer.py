from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from .timeline_renderer import TimelineRenderError, inject_timeline_into_dynamic_body
except ImportError:
    from timeline_renderer import TimelineRenderError, inject_timeline_into_dynamic_body  # type: ignore

SVG_NS = "http://www.w3.org/2000/svg"
NS = {"svg": SVG_NS}


class DriverLogRendererError(RuntimeError):
    """Raised when template parsing or file generation fails."""


_DYNAMIC_LAYER_BODY = re.compile(
    r"(<g\b[^>]*\bid=\"dynamic\"[^>]*>)(?P<body>.*?)(</g>)",
    re.DOTALL,
)
_TEXT_BLOCK = re.compile(
    r"(?P<open><text\b[^>]*\bid=\"(?P<id>[^\"]+)\"[^>]*>)(?P<content>.*?)(?P<close></text>)",
    re.DOTALL,
)
_TSPAN_BLOCK = re.compile(
    r"(?P<open><tspan\b[^>]*>)(?P<value>.*?)(?P<close></tspan>)",
    re.DOTALL,
)


def read_template_tree(template_path: Path) -> ET.ElementTree:
    if not template_path.exists():
        raise DriverLogRendererError(f"Template not found: {template_path}")
    return ET.parse(template_path)


def get_dynamic_text_nodes(tree: ET.ElementTree) -> list[ET.Element]:
    root = tree.getroot()
    dynamic_layer = root.find(".//svg:g[@id='dynamic']", NS)
    if dynamic_layer is None:
        raise DriverLogRendererError("Could not find <g id='dynamic'> in the template.")
    return dynamic_layer.findall("svg:text[@id]", NS)


def current_text_value(text_node: ET.Element) -> str:
    tspan = text_node.find("svg:tspan", NS)
    if tspan is not None and tspan.text is not None:
        return tspan.text
    return text_node.text or ""


def list_dynamic_fields(template_path: Path) -> list[dict[str, str]]:
    tree = read_template_tree(template_path)
    fields: list[dict[str, str]] = []

    for text_node in get_dynamic_text_nodes(tree):
        text_id = text_node.get("id")
        if not text_id:
            continue
        fields.append(
            {
                "id": text_id,
                "label": text_id.replace("-", " ").replace("_", " ").title(),
                "value": current_text_value(text_node),
            }
        )

    return fields


def write_filled_svg(
    template_path: Path,
    output_svg_path: Path,
    values: dict[str, str],
    timeline_svg: str | None = None,
) -> None:
    if not template_path.exists():
        raise DriverLogRendererError(f"Template not found: {template_path}")

    template_svg = template_path.read_text(encoding="utf-8")
    dynamic_layer = _DYNAMIC_LAYER_BODY.search(template_svg)
    if dynamic_layer is None:
        raise DriverLogRendererError("Could not find <g id='dynamic'> in the template.")

    dynamic_body = dynamic_layer.group("body")

    def replace_text_block(match: re.Match[str]) -> str:
        text_id = match.group("id")
        if text_id not in values:
            return match.group(0)

        escaped_value = escape(str(values[text_id]))
        current_content = match.group("content")

        if _TSPAN_BLOCK.search(current_content):
            updated_content = _TSPAN_BLOCK.sub(
                lambda tspan: f"{tspan.group('open')}{escaped_value}{tspan.group('close')}",
                current_content,
                count=1,
            )
        else:
            updated_content = escaped_value

        return f"{match.group('open')}{updated_content}{match.group('close')}"

    updated_dynamic_body = _TEXT_BLOCK.sub(replace_text_block, dynamic_body)

    if timeline_svg is not None:
        try:
            updated_dynamic_body = inject_timeline_into_dynamic_body(
                updated_dynamic_body,
                timeline_svg,
            )
        except TimelineRenderError as exc:
            raise DriverLogRendererError(str(exc)) from exc

    filled_svg = (
        template_svg[: dynamic_layer.start("body")]
        + updated_dynamic_body
        + template_svg[dynamic_layer.end("body") :]
    )

    output_svg_path.write_text(filled_svg, encoding="utf-8")


def convert_svg_to_pdf(output_svg_path: Path, output_pdf_path: Path) -> None:
    cairo_error: Exception | None = None

    try:
        import cairosvg  # Imported lazily so rsvg fallback still works.

        cairosvg.svg2pdf(url=str(output_svg_path), write_to=str(output_pdf_path))
        return
    except ImportError as exc:
        cairo_error = exc
    except Exception as exc:  # pragma: no cover - depends on system libs/fonts.
        cairo_error = exc

    try:
        subprocess.run(
            [
                "rsvg-convert",
                "-f",
                "pdf",
                "-o",
                str(output_pdf_path),
                str(output_svg_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DriverLogRendererError(
            "SVG->PDF conversion failed. Install `cairosvg` (pip) or `rsvg-convert` (system package)."
        ) from cairo_error or exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        message = "rsvg-convert failed"
        if stderr:
            message = f"{message}: {stderr}"
        raise DriverLogRendererError(message) from cairo_error or exc


def generate_driver_log(
    template_path: Path,
    output_svg_path: Path,
    output_pdf_path: Path,
    values: dict[str, str],
    timeline_svg: str | None = None,
) -> None:
    fields = list_dynamic_fields(template_path)
    allowed_values = {field["id"]: field["value"] for field in fields}

    for key, value in values.items():
        if key in allowed_values:
            allowed_values[key] = str(value)

    write_filled_svg(template_path, output_svg_path, allowed_values, timeline_svg=timeline_svg)
    convert_svg_to_pdf(output_svg_path, output_pdf_path)
