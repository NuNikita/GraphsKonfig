"""Parse and validate the command-line configuration."""

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

PACKAGE_PATTERN = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
TEST_PACKAGE_PATTERN = r"[A-Z]+"
VERSION_PATTERN = (
    r"[0-9]+(?:\.[0-9]+){0,3}"
    r"(?:-[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?"
    r"(?:\+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?"
)


def check_text(value):
    """Reject control characters that would break key-value output."""
    if any(not char.isprintable() for char in value):
        raise ValueError("управляющие символы запрещены")
    return value


def package_name(value):
    """Validate a package identifier without accessing a repository."""
    check_text(value)
    if not re.fullmatch(PACKAGE_PATTERN, value):
        raise ValueError("ожидается имя из латинских букв, цифр, _, . и -")
    return value


def package_version(value):
    """Validate a numeric version with optional prerelease and metadata."""
    check_text(value)
    if not re.fullmatch(VERSION_PATTERN, value):
        raise ValueError("ожидается версия, например 1.0.0 или 1.0.0-beta.1")
    return value


def repository_url(value):
    """Validate an HTTP(S) repository URL without making network requests."""
    check_text(value)
    if any(char.isspace() for char in value):
        raise ValueError("URL не должен содержать пробелы")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("ожидается URL репозитория с http:// или https://")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("учётные данные в URL не поддерживаются")
    if parsed.fragment:
        raise ValueError("фрагмент URL после # не поддерживается")
    if parsed.port is not None and not parsed.port:
        raise ValueError("порт должен быть положительным")
    return value


def repository_file(value):
    """Require an existing readable file in test-repository mode."""
    check_text(value)
    if not value.strip():
        raise ValueError("путь к тестовому репозиторию не должен быть пустым")
    path = Path(value).expanduser()
    if not path.is_file():
        raise ValueError("файл тестового репозитория не найден")
    with path.open("rb"):
        pass
    return value


def output_file(value):
    """Validate an SVG destination without creating or changing files."""
    check_text(value)
    path = Path(value).expanduser()
    if path.suffix.lower() != ".svg":
        raise ValueError("имя изображения должно иметь расширение .svg")
    if not path.parent.is_dir():
        raise ValueError("каталог для изображения не существует")
    if path.exists() and not path.is_file():
        raise ValueError("путь изображения должен указывать на файл")
    target = path if path.exists() else path.parent
    if not os.access(target, os.W_OK):
        raise ValueError("нет прав записи по пути изображения")
    return value


def filter_text(value):
    """Allow an empty filter; reject whitespace-only and control strings."""
    check_text(value)
    if value and not value.strip():
        raise ValueError("фильтр не должен состоять только из пробелов")
    return value


def create_parser():
    """Describe the six configurable parameters of variant 17."""
    parser = argparse.ArgumentParser(
        description="Вариант 17, этап 2: прямые зависимости NuGet-пакета.",
        allow_abbrev=False,
    )
    parser.add_argument("--package", required=True, help="имя пакета")
    parser.add_argument(
        "--repository", required=True, help="URL или путь к тестовому файлу"
    )
    parser.add_argument(
        "--test-mode", action="store_true", help="использовать тестовый файл"
    )
    parser.add_argument("--version", required=True, help="версия пакета")
    parser.add_argument(
        "--output", required=True, help="путь будущего SVG-изображения"
    )
    parser.add_argument(
        "--filter", default="", help="подстрока исключаемых пакетов"
    )
    return parser


def validate_option(parser, name, validator, value):
    """Report validation and filesystem errors as ordinary CLI errors."""
    try:
        return validator(value)
    except (ValueError, OSError) as error:
        parser.error(f"--{name}: {error}")


def parse_config(argv=None):
    """Parse arguments and validate all values and mode-dependent rules."""
    parser = create_parser()
    config = parser.parse_args(argv)
    validators = {
        "package": package_name,
        "version": package_version,
        "output": output_file,
        "filter": filter_text,
        "repository": repository_file if config.test_mode else repository_url,
    }
    for name, validator in validators.items():
        validate_option(parser, name, validator, getattr(config, name))
    if config.test_mode and not re.fullmatch(
        TEST_PACKAGE_PATTERN, config.package
    ):
        parser.error("--package: в тестовом режиме нужны большие буквы A-Z")
    return config
