from __future__ import annotations

from pathlib import Path

from scr.ocr.paddle_structured import recognize_to_structured_markdown


PROJECT_ROOT = Path(__file__).resolve().parent

TEST_ENV_FILE = PROJECT_ROOT / ".env"
TEST_FILE_PATH = PROJECT_ROOT / "Data" / "助剂对Ru:CeO2催化剂的表面性质及氨合成性能的影响.pdf"
TEST_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "ocr"
TEST_TIMEOUT = 180
TEST_VERBOSE = True
TEST_OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": True,
}


def test_ocr() -> None:
    print(f"[test_ocr] source file: {TEST_FILE_PATH}", flush=True)
    result_path = recognize_to_structured_markdown(
        file_path=TEST_FILE_PATH,
        env_file=TEST_ENV_FILE,
        output_root=TEST_OUTPUT_ROOT,
        timeout=TEST_TIMEOUT,
        optional_payload=TEST_OPTIONAL_PAYLOAD,
        verbose=TEST_VERBOSE,
    )
    print(f"[test_ocr] structured markdown: {result_path}", flush=True)


if __name__ == "__main__":
    test_ocr()
