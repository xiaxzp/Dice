from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import StorageError


class JsonStore:
    """Small JSON repository with UTF-8 and atomic replacement semantics."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, relative_path: str | os.PathLike[str]) -> dict[str, Any] | None:
        path = self._path(relative_path)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as stream:
                value = json.load(stream)
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"could not read JSON file {path}: {error}") from error
        if not isinstance(value, dict):
            raise StorageError(f"JSON root must be an object: {path}")
        return value

    def write(self, relative_path: str | os.PathLike[str], value: dict[str, Any]) -> None:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except (OSError, TypeError, ValueError) as error:
            raise StorageError(f"could not write JSON file {path}: {error}") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def delete(self, relative_path: str | os.PathLike[str]) -> bool:
        path = self._path(relative_path)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise StorageError(f"could not delete JSON file {path}: {error}") from error
        return True

    def _path(self, relative_path: str | os.PathLike[str]) -> Path:
        path = (self.root / Path(relative_path)).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise StorageError("repository path escapes its root")
        return path
