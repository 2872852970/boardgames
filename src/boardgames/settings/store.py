"""参数的校验与持久化。

存到 ``config/settings.json``；读取时逐项校验、裁剪越界值、丢弃未知键，
写入时用「临时文件 + os.replace」保证原子性。
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from boardgames.ai.engine import AIEngineParams
from boardgames.settings.schema import (
    ENGINE_PARAM_MAP,
    SPEC_BY_KEY,
    SPECS,
    WEIGHT_KEYS,
    Values,
)

SCHEMA_VERSION = 1


def default_settings_path() -> Path:
    """定位项目的 ``config/settings.json``（以 pyproject.toml 所在目录为准）。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent / "config" / "settings.json"
    return Path.cwd() / "config" / "settings.json"


def default_values() -> dict[str, Any]:
    return {spec.key: spec.default for spec in SPECS}


class Settings:
    """可观察的参数集合。"""

    def __init__(self, path: Path | None = None, values: dict[str, Any] | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()
        self.values = Values(default_values())
        if values:
            for key, value in values.items():
                if key in SPEC_BY_KEY:
                    self.values[key] = value
        self._listeners: list[Callable[[str, Any], None]] = []
        #: 只在本进程生效的临时覆盖（例如命令行参数）→ 不写回文件
        self._volatile: dict[str, Any] = {}

    # ---- 读写 ----

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        target = Path(path) if path is not None else default_settings_path()
        data: dict[str, Any] = {}
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                candidate = raw.get("params", raw)
                if isinstance(candidate, dict):
                    data = candidate
        except (OSError, ValueError):
            data = {}
        return cls(target, data)

    def save(self) -> None:
        params = self.values.as_dict()
        # 临时覆盖不落盘，写回各自的原值
        for key, original in self._volatile.items():
            params[key] = original
        payload = {
            "schema_version": SCHEMA_VERSION,
            "params": params,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=self.path.name + ".", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except OSError:
            # 配置写入失败不该影响游戏运行
            pass

    # ---- 访问 ----

    def get(self, key: str) -> Any:
        return self.values.get(key, SPEC_BY_KEY[key].default if key in SPEC_BY_KEY else None)

    def set(self, key: str, value: Any, *, notify: bool = True) -> Any:
        if key not in SPEC_BY_KEY:
            raise KeyError(f"未知参数: {key!r}")
        self.values[key] = value
        coerced = self.values[key]
        if notify:
            for listener in self._listeners:
                listener(key, coerced)
        return coerced

    def reset(self, *, notify: bool = True) -> None:
        for key, value in default_values().items():
            self.set(key, value, notify=False)
        if notify:
            for listener in self._listeners:
                listener("*", None)

    def on_change(self, listener: Callable[[str, Any], None]) -> None:
        self._listeners.append(listener)

    def set_volatile(self, key: str, value: Any) -> Any:
        """临时覆盖某个参数：本进程内生效，但**不写回配置文件**。

        命令行参数（``--size`` / ``--mode`` 等）走这条路径，
        避免"试跑一次"就把用户的配置改掉。
        """
        if key not in SPEC_BY_KEY:
            raise KeyError(f"未知参数: {key!r}")
        if key not in self._volatile:
            self._volatile[key] = self.values.get(key)
        return self.set(key, value)

    # ---- 派生对象 ----

    def weights(self) -> dict[str, float]:
        return {key: float(self.values[key]) for key in WEIGHT_KEYS}

    def engine_params(self, engine_key: str) -> AIEngineParams:
        """按引擎类型组装 AIEngineParams。"""
        kwargs: dict[str, Any] = {}
        for field, spec_key in ENGINE_PARAM_MAP.get(engine_key, {}).items():
            kwargs[field] = self.values[spec_key]
        seed = int(self.values.get("ai_seed", 0))
        kwargs["seed"] = None if seed <= 0 else seed
        kwargs["weights"] = self.weights()
        return AIEngineParams(**kwargs)

    # ---- 便于测试 ----

    def as_dict(self) -> dict[str, Any]:
        return self.values.as_dict()
