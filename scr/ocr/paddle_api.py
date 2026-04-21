from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_ENV_FILE = PROJECT_ROOT / ".env"
TEST_FILE_PATH = PROJECT_ROOT / "Data" / "助剂对Ru:CeO2催化剂的表面性质及氨合成性能的影响.pdf"
TEST_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "ocr"
TEST_TIMEOUT = 180
TEST_OPTIONAL_PAYLOAD: dict[str, Any] | None = None
TEST_DOWNLOAD_ASSETS = True
TEST_VERBOSE = True


class PaddleOCRAPIError(RuntimeError):
    """Raised when the PaddleOCR API request or response is invalid."""


class PaddleOCRAPIClient:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: int = 180,
        session: requests.sessions.Session | Any | None = None,
    ) -> None:
        if not api_url:
            raise ValueError("api_url is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls, env_file: str | Path | None = None, timeout: int = 180) -> "PaddleOCRAPIClient":
        if env_file:
            _load_env_file(env_file)

        api_url = os.environ.get("PADDLEOCR_VL_API_URL", "").strip()
        api_key = os.environ.get("PADDLEOCR_VL_API_KEY", "").strip()
        return cls(api_url=api_url, api_key=api_key, timeout=timeout)

    def recognize(
        self,
        file_path: str | Path,
        optional_payload: dict[str, Any] | None = None,
        verbose: bool = False,
    ) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(path)

        payload = {
            "file": base64.b64encode(path.read_bytes()).decode("ascii"),
            "fileType": _detect_file_type(path),
        }
        if optional_payload:
            payload.update(optional_payload)

        headers = {
            "Authorization": f"token {self.api_key}",
            "Content-Type": "application/json",
        }

        if verbose:
            print(f"Submitting OCR request: {path}")

        response = self.session.post(
            self.api_url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as exc:
            raise PaddleOCRAPIError("PaddleOCR API did not return valid JSON") from exc

        if not isinstance(data, dict):
            raise PaddleOCRAPIError("PaddleOCR API returned an unexpected payload type")
        if verbose:
            result_count = len((((data.get("result") or {}).get("layoutParsingResults")) or []))
            print(f"OCR response received: {result_count} page result(s)")
        return data

    def recognize_to_markdown(
        self,
        file_path: str | Path,
        output_dir: str | Path,
        output_md_path: str | Path | None = None,
        optional_payload: dict[str, Any] | None = None,
        download_assets: bool = True,
        verbose: bool = False,
    ) -> str | Path:
        data = self.recognize(
            file_path=file_path,
            optional_payload=optional_payload,
            verbose=verbose,
        )
        return self.write_ocr_outputs(
            data=data,
            output_dir=output_dir,
            output_md_path=output_md_path,
            download_assets=download_assets,
            verbose=verbose,
        )

    def write_ocr_outputs(
        self,
        data: dict[str, Any],
        output_dir: str | Path,
        output_md_path: str | Path | None = None,
        download_assets: bool = True,
        verbose: bool = False,
    ) -> str | Path:

        try:
            parsing_results = data["result"]["layoutParsingResults"]
        except (KeyError, TypeError) as exc:
            raise PaddleOCRAPIError("PaddleOCR API response is missing layoutParsingResults") from exc

        if not isinstance(parsing_results, list):
            raise PaddleOCRAPIError("layoutParsingResults must be a list")

        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)

        markdown_parts: list[str] = []
        for index, page in enumerate(parsing_results):
            markdown = ((page or {}).get("markdown") or {}).get("text", "")
            if markdown:
                markdown_parts.append(markdown)

            if not download_assets:
                continue

            for relative_path, asset_url in (((page or {}).get("markdown") or {}).get("images") or {}).items():
                self._download_asset(asset_url, output_root / relative_path)
                if verbose:
                    print(f"Saved markdown asset: {output_root / relative_path}")

            for asset_name, asset_url in (((page or {}).get("outputImages") or {}).items()):
                self._download_asset(asset_url, output_root / f"{asset_name}_{index}.jpg")
                if verbose:
                    print(f"Saved page asset: {output_root / f'{asset_name}_{index}.jpg'}")

        final_markdown = "\n\n---\n\n".join(markdown_parts)

        if output_md_path is None:
            return final_markdown

        md_path = Path(output_md_path)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(final_markdown, encoding="utf-8")
        if verbose:
            print(f"Saved markdown: {md_path}")
        return md_path

    def _download_asset(self, asset_url: str, destination: Path) -> None:
        if not asset_url:
            return

        response = self.session.get(asset_url, timeout=60)
        response.raise_for_status()

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)


def _detect_file_type(file_path: Path) -> int:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return 0
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
        return 1
    raise ValueError(f"Unsupported file type for PaddleOCR API: {suffix}")


def _load_env_file(env_file: str | Path) -> None:
    path = Path(env_file)
    if not path.exists():
        raise FileNotFoundError(path)

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _now() -> datetime:
    return datetime.now()


def _slugify_filename(file_path: str | Path) -> str:
    stem = Path(file_path).stem
    normalized = unicodedata.normalize("NFKC", stem)
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", normalized)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "document"


def _build_run_output_paths(
    file_path: str | Path,
    artifacts_root: str | Path,
    timestamp: datetime | None = None,
) -> tuple[Path, Path, Path, Path]:
    ts = timestamp or _now()
    doc_slug = _slugify_filename(file_path)
    run_dir = Path(artifacts_root) / doc_slug / f"run_{ts.strftime('%Y%m%d_%H%M%S')}"
    return (
        run_dir,
        run_dir / "document.md",
        run_dir / "raw_response.json",
        run_dir / "assets",
    )


def main() -> int:
    client = PaddleOCRAPIClient.from_env(env_file=TEST_ENV_FILE, timeout=TEST_TIMEOUT)
    run_dir, output_md_path, raw_response_path, assets_dir = _build_run_output_paths(
        file_path=TEST_FILE_PATH,
        artifacts_root=TEST_OUTPUT_ROOT,
    )
    data = client.recognize(
        file_path=TEST_FILE_PATH,
        optional_payload=TEST_OPTIONAL_PAYLOAD,
        verbose=TEST_VERBOSE,
    )
    result = client.write_ocr_outputs(
        data=data,
        output_dir=assets_dir,
        output_md_path=output_md_path,
        download_assets=TEST_DOWNLOAD_ASSETS,
        verbose=TEST_VERBOSE,
    )
    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    raw_response_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if TEST_VERBOSE:
        print(f"Saved raw response: {raw_response_path}")
        print(f"Run directory: {run_dir}")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
