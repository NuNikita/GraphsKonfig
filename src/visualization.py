"""Describe a dependency graph in PlantUML and render it as SVG."""

import os
import subprocess
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree

RENDER_TIMEOUT = 30
SVG_TAG = "{http://www.w3.org/2000/svg}svg"


class VisualizationError(Exception):
    """Describe a rendering or SVG output failure for the CLI."""


def format_plantuml(graph):
    """Generate one node per package version, followed by dependency arrows."""
    aliases = {package: f"p{index}" for index, package in enumerate(graph)}
    lines = ["@startuml", "!pragma layout smetana", "left to right direction"]
    if not aliases:
        lines.append('note "Граф пуст: исходный пакет исключён фильтром" as n0')
    for package, alias in aliases.items():
        lines.append(f'rectangle "{package.label()}" as {alias}')
    for package, dependencies in graph.items():
        for target in dependencies:
            lines.append(f"{aliases[package]} --> {aliases[target]}")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def render_svg(diagram):
    """Run local PlantUML and return its validated SVG output as bytes."""
    jar = os.environ.get("PLANTUML_JAR")
    command = ["java", "-Djava.awt.headless=true", "-jar", jar] if jar else [
        "plantuml",
    ]
    command += ["-pipe", "-tsvg", "-charset", "UTF-8", "-failfast2"]
    try:
        result = subprocess.run(
            command, input=diagram.encode("utf-8"), capture_output=True,
            check=True, timeout=RENDER_TIMEOUT,
        )
    except FileNotFoundError as error:
        message = (
            "установите PlantUML или укажите PLANTUML_JAR "
            "и добавьте Java в PATH"
        )
        raise VisualizationError(message) from error
    except subprocess.TimeoutExpired as error:
        message = f"PlantUML не завершился за {RENDER_TIMEOUT} с"
        raise VisualizationError(message) from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.decode("utf-8", errors="replace").strip()
        message = f"ошибка PlantUML (код {error.returncode})"
        if details:
            message = f"{message}: {details}"
        raise VisualizationError(message) from error
    except OSError as error:
        message = f"не удалось запустить PlantUML: {error}"
        raise VisualizationError(message) from error
    try:
        if ElementTree.fromstring(result.stdout).tag == SVG_TAG:
            return result.stdout
    except ElementTree.ParseError as error:
        raise VisualizationError("PlantUML вернул некорректный SVG") from error
    raise VisualizationError("в документе PlantUML нет корневого элемента SVG")


def save_svg(diagram, output):
    """Replace the destination only after rendering and writing succeed."""
    content = render_svg(diagram)
    path = Path(output).expanduser()
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    except OSError as error:
        message = f"не удалось сохранить SVG: {error}"
        raise VisualizationError(message) from error
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
