"""发布安装路径的安全下限合同。

wheel 元数据只发布 ``project.dependencies``；``[tool.uv]`` 的约束/覆盖不会进入
PyPI 分发，因此 runtime floor 必须直接落在 dependencies，Docker 构建固定 uv 版本。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 传递依赖无法在 dependencies 里自然表达，按已修复版本钉下限（与旧 candidate 一致）
RUNTIME_FLOORS = {
    "multidict": ">=6.9.1",
    "pymongo": ">=4.18.2",
    "certifi": ">=2026.10.19",
    "urllib3": ">=2.8.0",
    "pyjwt": ">=2.15.1",
    "virtualenv": ">=21.14.7",
    "aiohttp": ">=3.14.4",
    "pillow": "==13.0.0",
}


def direct_requirements() -> dict[str, Requirement]:
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = [Requirement(raw) for raw in config["project"]["dependencies"]]
    return {requirement.name.lower(): requirement for requirement in requirements}


@pytest.mark.parametrize(("name", "specifier"), sorted(RUNTIME_FLOORS.items()))
def test_runtime_floor_is_published_in_project_dependencies(name: str, specifier: str) -> None:
    requirements = direct_requirements()
    assert name in requirements, f"{name} must be a direct dependency to reach wheel metadata"
    assert str(requirements[name].specifier) == specifier


def test_embedding_extra_keeps_fastembed_pin() -> None:
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    embedding = [Requirement(raw) for raw in config["project"]["optional-dependencies"]["embedding-local"]]
    assert [(req.name.lower(), str(req.specifier)) for req in embedding] == [("fastembed", "==0.8.0")]


def test_dockerfile_pins_base_image_python_and_uv() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG BASE_IMAGE=python:3.12.15-slim" in dockerfile
    # 顶部国内示例与默认基础镜像版本一致
    assert "docker.m.daocloud.io/library/python:3.12.15-slim" in dockerfile
    # 安装 uv 必须精确固定，不能随 pip 浮动
    assert dockerfile.count('"uv==0.13.4"') == 2, "both index branches must pin uv==0.13.4"
    assert "pip install uv;" not in dockerfile
    # 保持既有 UV_DEFAULT_INDEX 设计
    assert dockerfile.count("--index-url \"$UV_DEFAULT_INDEX\"") == 2
    assert "uv pip install --system" in dockerfile
