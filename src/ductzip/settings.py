"""Per-user settings for DuctZip (v0.7).

Settings live in a small JSON document in a per-user location:

- Windows: ``%APPDATA%\\DuctZip\\settings.json``
- Other platforms: ``~/.ductzip/settings.json``

The ``DUCTZIP_SETTINGS_PATH`` environment variable overrides the location
(portable mode and tests). Settings are plain data: passwords are never
stored here, and nothing in this module touches the network.

Corrupt-file recovery: if the JSON cannot be decoded (or the top-level
value is not an object), the corrupt file is renamed to
``settings.json.corrupt`` and defaults are returned. Losing preferences is
acceptable; crashing or hanging on startup is not.

Precedence at runtime: explicit CLI flag > settings value > built-in
default. A configured ``sevenzip_path`` that no longer exists falls back to
normal backend discovery instead of failing hard.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path

OVERWRITE_POLICIES = ("skip", "overwrite", "rename")
CONFLICT_STRATEGIES = ("merge", "rename", "cancel")

_SETTINGS_ENV_VAR = "DUCTZIP_SETTINGS_PATH"
CORRUPT_SUFFIX = ".corrupt"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Settings:
    """Durable user preferences. ``None``/empty means "not configured".

    ``smart_output=None`` keeps each surface's documented built-in default
    (CLI ``extract``: off unless ``--smart-output``; GUI and batch: on), so
    loading settings never silently changes CLI behavior. ``sevenzip_path``
    empty/None means "use normal backend discovery".
    """

    sevenzip_path: str | None = None
    overwrite_policy: str = "skip"
    conflict_strategy: str = "merge"
    smart_output: bool | None = None


@dataclass(frozen=True)
class LoadResult:
    settings: Settings
    path: Path
    corrupt_recovered: bool = False


def settings_path() -> Path:
    override = os.environ.get(_SETTINGS_ENV_VAR)
    if override:
        return Path(override)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "DuctZip" / "settings.json"
    return Path.home() / ".ductzip" / "settings.json"


def load_settings(path: Path | None = None) -> LoadResult:
    """Load settings, recovering from a corrupt file by resetting to defaults."""
    target = path or settings_path()
    if not target.is_file():
        return LoadResult(Settings(), target)

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return LoadResult(_reset_corrupt(target), target, corrupt_recovered=True)

    if not isinstance(raw, dict):
        return LoadResult(_reset_corrupt(target), target, corrupt_recovered=True)
    return LoadResult(_settings_from_dict(raw), target)


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    """Persist settings atomically (temp file + rename in the same directory)."""
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SCHEMA_VERSION,
        "sevenzip_path": settings.sevenzip_path,
        "overwrite_policy": settings.overwrite_policy,
        "conflict_strategy": settings.conflict_strategy,
        "smart_output": settings.smart_output,
    }
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def set_value(settings: Settings, key: str, value: str) -> Settings:
    """Return a copy of ``settings`` with ``key`` set to ``value``.

    Raises ``ValueError`` with a user-facing message for unknown keys or
    invalid values. ``sevenzip_path`` must name an existing file so a typo
    cannot silently redirect extraction to the wrong executable.
    """
    if key == "sevenzip_path":
        candidate = Path(value)
        if not candidate.is_file():
            raise ValueError(f"7-Zip 路径不存在：{value}")
        return replace(settings, sevenzip_path=str(candidate.resolve()))
    if key == "overwrite_policy":
        if value not in OVERWRITE_POLICIES:
            raise ValueError(f"overwrite_policy 必须是 {'/'.join(OVERWRITE_POLICIES)} 之一")
        return replace(settings, overwrite_policy=value)
    if key == "conflict_strategy":
        if value not in CONFLICT_STRATEGIES:
            raise ValueError(f"conflict_strategy 必须是 {'/'.join(CONFLICT_STRATEGIES)} 之一")
        return replace(settings, conflict_strategy=value)
    if key == "smart_output":
        if value.lower() not in ("true", "false"):
            raise ValueError("smart_output 必须是 true 或 false")
        return replace(settings, smart_output=value.lower() == "true")
    raise ValueError(f"未知设置项：{key}（可选：sevenzip_path/overwrite_policy/conflict_strategy/smart_output）")


def unset_value(settings: Settings, key: str) -> Settings:
    """Return a copy of ``settings`` with ``key`` reset to its built-in default."""
    defaults = Settings()
    if key == "sevenzip_path":
        return replace(settings, sevenzip_path=defaults.sevenzip_path)
    if key == "overwrite_policy":
        return replace(settings, overwrite_policy=defaults.overwrite_policy)
    if key == "conflict_strategy":
        return replace(settings, conflict_strategy=defaults.conflict_strategy)
    if key == "smart_output":
        return replace(settings, smart_output=defaults.smart_output)
    raise ValueError(f"未知设置项：{key}（可选：sevenzip_path/overwrite_policy/conflict_strategy/smart_output）")


def effective_sevenzip(settings: Settings) -> str | None:
    """The configured backend path if it still exists, else ``None``.

    A stale configured path falls back to normal discovery rather than
    failing hard; ``settings set`` already validates at write time.
    """
    if settings.sevenzip_path and Path(settings.sevenzip_path).is_file():
        return settings.sevenzip_path
    return None


def _settings_from_dict(raw: dict) -> Settings:
    defaults = Settings()

    def _str(key: str) -> str | None:
        value = raw.get(key)
        return value if isinstance(value, str) and value else None

    def _enum(key: str, allowed: tuple[str, ...], fallback: str) -> str:
        value = raw.get(key)
        return value if isinstance(value, str) and value in allowed else fallback

    smart = raw.get("smart_output")
    return Settings(
        sevenzip_path=_str("sevenzip_path"),
        overwrite_policy=_enum("overwrite_policy", OVERWRITE_POLICIES, defaults.overwrite_policy),
        conflict_strategy=_enum("conflict_strategy", CONFLICT_STRATEGIES, defaults.conflict_strategy),
        smart_output=smart if isinstance(smart, bool) else None,
    )


def _reset_corrupt(target: Path) -> Settings:
    backup = target.with_name(target.name + CORRUPT_SUFFIX)
    try:
        os.replace(target, backup)
    except OSError:
        # If the corrupt file cannot be moved aside, leave it in place and
        # still run on defaults; preferences are expendable, startup is not.
        pass
    return Settings()
