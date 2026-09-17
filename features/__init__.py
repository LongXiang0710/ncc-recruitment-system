"""Discover business features without hard-coding them in the server core."""
from __future__ import annotations

import json
from importlib import import_module
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True)
class Feature:
    name: str
    label: str
    order: int
    dependencies: tuple[str, ...]
    schema: dict
    directory: Path
    service: ModuleType
    enabled: bool


def load_features(root: Path) -> dict[str, Feature]:
    """Load enabled feature folders and validate cross-feature dependencies."""
    config_path = root / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    disabled = set(config.get('disabled', []))
    discovered: list[Feature] = []
    for manifest_path in sorted(root.glob('*/manifest.json')):
        directory = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        name = manifest.get('name')
        if not isinstance(name, str) or name != directory.name or not name.replace('_', '').isalnum():
            raise RuntimeError(f'功能目录 {directory} 的名称无效')
        schema_path = directory / 'schema.json'
        discovered.append(Feature(
            name=name,
            label=str(manifest.get('label') or name),
            order=int(manifest.get('order', 100)),
            dependencies=tuple(manifest.get('dependencies', [])),
            schema=json.loads(schema_path.read_text(encoding='utf-8')),
            directory=directory,
            service=import_module(f'features.{name}.service'),
            enabled=name not in disabled,
        ))
    features = {feature.name: feature for feature in sorted(discovered, key=lambda item: (item.order, item.name))}
    missing = {
        name: [dependency for dependency in feature.dependencies if dependency not in features]
        for name, feature in features.items()
    }
    missing = {name: dependencies for name, dependencies in missing.items() if dependencies}
    if missing:
        details = '；'.join(f"{name} 依赖 {','.join(dependencies)}" for name, dependencies in missing.items())
        raise RuntimeError('功能依赖未满足：' + details)
    unknown = disabled - set(features)
    if unknown:
        raise RuntimeError('停用列表包含未知功能：' + ','.join(sorted(unknown)))
    return features
