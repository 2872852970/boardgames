"""测试收集钩子：给耗时用例统一打 ``slow`` 标记。

判据是**路径**，不给每个用例手写装饰器 ——
"跑真 AI 搜索"和"跑整局 rollout"这两类东西总是长在同一个目录下。

```bash
uv run pytest                # 全部（提 PR / 改引擎 / 改规则时用）
uv run pytest -m "not slow"  # 只跑快的：规则、UI、参数、设置（日常改动用这个）
uv run pytest -m slow        # 只跑耗时的：AI 搜索契约、整局自对弈收敛
```
"""

from __future__ import annotations

import pytest

#: 命中这些片段的用例算"耗时"（AI 搜索与整局 rollout 模拟）
_SLOW_PARTS = ("/tests/ai/", "rollout", "benchmark")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if any(part in path for part in _SLOW_PARTS):
            item.add_marker(pytest.mark.slow)
