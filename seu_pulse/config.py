from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    collector: str
    url: str
    enabled: bool = True
    category: str = "通知"
    route: str | None = None
    timeout: float = 15
    interval_seconds: float = 1800
    request_interval_seconds: float = 1
    retries: int = 1
    # HTML adapter is deliberately limited to WebPlus public article lists.
    allow_empty: bool = False
    max_items: int = 20
    content_classes: tuple[str, ...] = ("wp_articlecontent", "Article_Content")
    list_container_id: str | None = None
    list_container_class: str | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.id):
            raise ConfigError("来源 id 只能包含小写字母、数字、下划线及连字符")
        if self.collector not in {"rsshub", "html", "webplus"}:
            raise ConfigError(f"来源 {self.id}: 不支持的采集器")
        for value in (self.name, self.category):
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"来源 {self.id}: 名称和分类不能为空")
        validate_url(self.url)
        if type(self.enabled) is not bool or type(self.allow_empty) is not bool:
            raise ConfigError(f"来源 {self.id}: enabled/allow_empty 必须为布尔值")
        if self.collector == "rsshub" and (
            not isinstance(self.route, str) or not self.route.startswith("/")
            or self.route.startswith("//") or ".." in self.route
            or urlsplit(self.route).scheme or urlsplit(self.route).netloc
        ):
            raise ConfigError(f"来源 {self.id}: RSSHub route 必须为绝对路径")
        for key in ("timeout", "interval_seconds", "request_interval_seconds"):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ConfigError(f"来源 {self.id}: {key} 必须为有限非负数字")
        if self.timeout <= 0:
            raise ConfigError(f"来源 {self.id}: timeout 必须大于零")
        if type(self.retries) is not int or not 0 <= self.retries <= 3:
            raise ConfigError(f"来源 {self.id}: retries 必须在 0..3")
        if type(self.max_items) is not int or not 1 <= self.max_items <= 100:
            raise ConfigError(f"来源 {self.id}: max_items 必须在 1..100")
        if (not isinstance(self.content_classes, (tuple, list)) or not 1 <= len(self.content_classes) <= 4
                or not all(isinstance(c, str) and re.fullmatch(r"[A-Za-z_][\w-]*", c) for c in self.content_classes)):
            raise ConfigError(f"来源 {self.id}: content_classes 必须为 1..4 个 HTML 类名")
        for name in ("list_container_id", "list_container_class"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][\w-]*", value)):
                raise ConfigError(f"来源 {self.id}: {name} 必须为 HTML 标识符")


def validate_url(url: str):
    if not isinstance(url, str):
        raise ConfigError("网址必须为字符串")
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        _ = parts.port
        if parts.query or parts.fragment:
            raise ValueError()
    except ValueError as exc:
        raise ConfigError("网址必须是无凭据、无查询参数和片段的 HTTP(S) 地址") from exc


@dataclass(frozen=True)
class Config:
    database: Path
    rsshub_base_url: str | None = None
    sources: tuple[SourceConfig, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.rsshub_base_url is not None:
            validate_url(self.rsshub_base_url)
        if any(s.collector == "rsshub" for s in self.sources) and self.rsshub_base_url is None:
            raise ConfigError("配置 RSSHub 来源时必须提供 RSSHub 服务地址")
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ConfigError("来源 id 重复")


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    try:
        with path.open("rb") as stream:
            # tomli 1.x uses a text file; loads works consistently on Python 3.10+.
            data = tomllib.loads(stream.read().decode("utf-8"))
        if set(data) - {"app", "sources"}:
            raise ConfigError("未知顶层配置项")
        app = data.get("app", {})
        if set(app) - {"database", "rsshub_base_url"}:
            raise ConfigError("未知 app 配置项")
        database = app.get("database", "data/seu-pulse.db")
        if not isinstance(database, str) or not database.strip():
            raise ConfigError("数据库路径不能为空")
        db = Path(database).expanduser()
        if not db.is_absolute():
            db = path.parent / db
        sources = tuple(SourceConfig(**row) for row in data.get("sources", []))
        base = app.get("rsshub_base_url", "https://rsshub.app" if any(s.collector == "rsshub" for s in sources) else None)
        return Config(db, base, sources)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"无法读取配置: {type(exc).__name__}") from exc
