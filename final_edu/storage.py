from __future__ import annotations

import json
import shutil
from pathlib import Path

try:
    import boto3
except ImportError:  # pragma: no cover - production installs boto3, local fallback does not need it.
    boto3 = None

from final_edu.config import Settings, get_settings


class ObjectStorage:
    def put_file(self, key: str, source_path: Path, content_type: str | None = None) -> None:
        raise NotImplementedError

    def put_json(self, key: str, payload: dict) -> None:
        raise NotImplementedError

    def get_json(self, key: str) -> dict:
        raise NotImplementedError

    def download_to_path(self, key: str, destination: Path) -> Path:
        raise NotImplementedError

    def delete_key(self, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self, prefix: str = "") -> list[str]:
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> int:
        raise NotImplementedError


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put_file(self, key: str, source_path: Path, content_type: str | None = None) -> None:
        target = self._resolve(key)
        shutil.copyfile(source_path, target)

    def put_json(self, key: str, payload: dict) -> None:
        target = self._resolve(key)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_json(self, key: str) -> dict:
        target = self._resolve(key)
        return json.loads(target.read_text(encoding="utf-8"))

    def download_to_path(self, key: str, destination: Path) -> Path:
        target = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, destination)
        return destination

    def delete_key(self, key: str) -> bool:
        target = self._absolute_path(key)
        if not target.exists():
            return False
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        self._prune_empty_parents(target.parent)
        return True

    def list_keys(self, prefix: str = "") -> list[str]:
        normalized_prefix = str(prefix or "").strip().lstrip("/")
        base_path = self.root if not normalized_prefix else self._absolute_path(normalized_prefix)
        if not base_path.exists():
            return []
        if base_path.is_file():
            return [str(base_path.relative_to(self.root)).replace("\\", "/")]
        return sorted(
            str(path.relative_to(self.root)).replace("\\", "/")
            for path in base_path.rglob("*")
            if path.is_file()
        )

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_keys(prefix)
        if not keys:
            return 0
        for key in keys:
            self.delete_key(key)
        normalized_prefix = str(prefix or "").strip().lstrip("/")
        if normalized_prefix:
            prefix_path = self._absolute_path(normalized_prefix)
            if prefix_path.exists() and prefix_path.is_dir():
                shutil.rmtree(prefix_path, ignore_errors=True)
                self._prune_empty_parents(prefix_path.parent)
        return len(keys)

    def _resolve(self, key: str) -> Path:
        relative_key = Path(key)
        self._validate_relative_key(relative_key)
        destination = self.root / relative_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def _absolute_path(self, key: str) -> Path:
        relative_key = Path(str(key or "").strip().lstrip("/"))
        self._validate_relative_key(relative_key)
        return self.root / relative_key

    def _prune_empty_parents(self, path: Path) -> None:
        current = path
        while current != self.root and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _validate_relative_key(self, key: Path) -> None:
        if key.is_absolute():
            raise ValueError("스토리지 키는 절대 경로일 수 없습니다.")
        for component in key.parts:
            if component in {"", ".", ".."}:
                raise ValueError(f"스토리지 키 구성요소가 올바르지 않습니다. ({component!r})")
            if len(component.encode("utf-8")) > 240:
                raise ValueError(f"스토리지 키 구성요소가 너무 깁니다. ({component[:48]}...)")


class R2ObjectStorage(ObjectStorage):
    def __init__(self, settings: Settings) -> None:
        if boto3 is None:
            raise RuntimeError("R2 스토리지를 사용하려면 boto3가 필요합니다.")
        self.bucket = settings.r2_bucket or ""
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name=settings.r2_region,
        )

    def put_file(self, key: str, source_path: Path, content_type: str | None = None) -> None:
        extra_args = {"ContentType": content_type} if content_type else None
        if extra_args:
            self.client.upload_file(str(source_path), self.bucket, key, ExtraArgs=extra_args)
            return
        self.client.upload_file(str(source_path), self.bucket, key)

    def put_json(self, key: str, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json; charset=utf-8",
        )

    def get_json(self, key: str) -> dict:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))

    def download_to_path(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(destination))
        return destination

    def delete_key(self, key: str) -> bool:
        normalized_key = str(key or "").strip().lstrip("/")
        if not normalized_key:
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=normalized_key)
        except Exception:  # noqa: BLE001
            return False
        return True

    def list_keys(self, prefix: str = "") -> list[str]:
        normalized_prefix = str(prefix or "").strip().lstrip("/")
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=normalized_prefix):
            for item in page.get("Contents", []) or []:
                key = str(item.get("Key") or "").strip()
                if key:
                    keys.append(key)
        return sorted(keys)

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_keys(prefix)
        if not keys:
            return 0
        for start in range(0, len(keys), 1000):
            chunk = keys[start : start + 1000]
            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
            )
        return len(keys)


def create_object_storage(settings: Settings | None = None) -> ObjectStorage:
    active_settings = settings or get_settings()
    if active_settings.storage_mode == "r2":
        return R2ObjectStorage(active_settings)
    return LocalObjectStorage(active_settings.runtime_dir / "object_store")
