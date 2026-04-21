import base64
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from scr.ocr.paddle_api import PaddleOCRAPIClient, _build_run_output_paths, main


class PaddleOCRAPITestCase(unittest.TestCase):
    def _build_success_session(self) -> Mock:
        post_response = Mock()
        post_response.raise_for_status.return_value = None
        post_response.json.return_value = {
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {
                            "text": "# Page 1",
                            "images": {
                                "figures/figure-1.png": "https://example.com/assets/figure-1.png",
                            },
                        },
                        "outputImages": {
                            "page-preview": "https://example.com/assets/page-preview.jpg",
                        },
                    }
                ]
            }
        }

        session = Mock()
        session.post.return_value = post_response
        session.get.side_effect = [
            Mock(content=b"png-bytes", raise_for_status=Mock()),
            Mock(content=b"jpg-bytes", raise_for_status=Mock()),
        ]
        return session

    def test_recognize_to_markdown_writes_markdown_and_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")
            session = self._build_success_session()

            client = PaddleOCRAPIClient(
                api_url="https://example.com/layout-parsing",
                api_key="secret",
                session=session,
            )

            output_dir = tmp_path / "artifacts"
            output_md_path = output_dir / "document.md"
            saved_md_path = client.recognize_to_markdown(
                file_path=pdf_path,
                output_dir=output_dir,
                output_md_path=output_md_path,
                optional_payload={"parse_mode": "layout"},
            )

            self.assertEqual(saved_md_path, output_md_path)
            self.assertEqual(output_md_path.read_text(encoding="utf-8"), "# Page 1")
            self.assertEqual(
                (output_dir / "figures" / "figure-1.png").read_bytes(),
                b"png-bytes",
            )
            self.assertEqual(
                (output_dir / "page-preview_0.jpg").read_bytes(),
                b"jpg-bytes",
            )

            _, kwargs = session.post.call_args
            self.assertEqual(kwargs["headers"]["Authorization"], "token secret")
            self.assertEqual(kwargs["json"]["fileType"], 0)
            self.assertEqual(kwargs["json"]["parse_mode"], "layout")
            self.assertEqual(
                kwargs["json"]["file"],
                base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
            )

    def test_recognize_to_markdown_prints_debug_logs_when_verbose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")
            output_dir = tmp_path / "artifacts"
            output_md_path = output_dir / "document.md"

            client = PaddleOCRAPIClient(
                api_url="https://example.com/layout-parsing",
                api_key="secret",
                session=self._build_success_session(),
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                client.recognize_to_markdown(
                    file_path=pdf_path,
                    output_dir=output_dir,
                    output_md_path=output_md_path,
                    verbose=True,
                )

            self.assertIn("Submitting OCR request", stdout.getvalue())
            self.assertIn("Saved markdown", stdout.getvalue())

    def test_build_run_output_paths_creates_readable_run_directory(self) -> None:
        pdf_path = Path("/tmp/助剂对Ru:CeO2催化剂的表面性质及氨合成性能的影响.pdf")
        artifacts_root = Path("/tmp/artifacts/ocr")
        timestamp = datetime(2026, 3, 31, 4, 5, 6)

        run_dir, output_md_path, raw_response_path, assets_dir = _build_run_output_paths(
            file_path=pdf_path,
            artifacts_root=artifacts_root,
            timestamp=timestamp,
        )

        self.assertEqual(run_dir, artifacts_root / "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响" / "run_20260331_040506")
        self.assertEqual(output_md_path, run_dir / "document.md")
        self.assertEqual(raw_response_path, run_dir / "raw_response.json")
        self.assertEqual(assets_dir, run_dir / "assets")

    def test_main_runs_cli_and_prints_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")
            run_dir = tmp_path / "artifacts" / "ocr" / "paper" / "run_20260331_040506"
            output_md_path = run_dir / "document.md"
            raw_response_path = run_dir / "raw_response.json"
            assets_dir = run_dir / "assets"

            fake_client = Mock()
            fake_client.recognize.return_value = {
                "result": {
                    "layoutParsingResults": [
                        {
                            "markdown": {
                                "text": "# Page 1",
                                "images": {
                                    "figures/figure-1.png": "https://example.com/assets/figure-1.png",
                                },
                            },
                            "outputImages": {
                                "page-preview": "https://example.com/assets/page-preview.jpg",
                            },
                        }
                    ]
                }
            }
            fake_client.write_ocr_outputs.return_value = output_md_path

            stdout = io.StringIO()
            with patch("scr.ocr.paddle_api.PaddleOCRAPIClient.from_env", return_value=fake_client):
                with patch("scr.ocr.paddle_api.TEST_ENV_FILE", tmp_path / ".env"):
                    with patch("scr.ocr.paddle_api.TEST_FILE_PATH", pdf_path):
                        with patch("scr.ocr.paddle_api.TEST_OUTPUT_ROOT", tmp_path / "artifacts" / "ocr"):
                            with patch("scr.ocr.paddle_api.TEST_TIMEOUT", 90):
                                with patch("scr.ocr.paddle_api.TEST_OPTIONAL_PAYLOAD", {"parse_mode": "layout"}):
                                    with patch("scr.ocr.paddle_api.TEST_DOWNLOAD_ASSETS", False):
                                        with patch("scr.ocr.paddle_api.TEST_VERBOSE", False):
                                            with patch("scr.ocr.paddle_api._now", return_value=datetime(2026, 3, 31, 4, 5, 6)):
                                                with redirect_stdout(stdout):
                                                    exit_code = main()

            self.assertEqual(exit_code, 0)
            self.assertIn(str(output_md_path), stdout.getvalue())
            self.assertEqual(raw_response_path.exists(), True)
            self.assertEqual(assets_dir.exists(), False)
            fake_client.recognize.assert_called_once_with(
                file_path=pdf_path,
                optional_payload={"parse_mode": "layout"},
                verbose=False,
            )
            fake_client.write_ocr_outputs.assert_called_once_with(
                data=fake_client.recognize.return_value,
                output_dir=assets_dir,
                output_md_path=output_md_path,
                download_assets=False,
                verbose=False,
            )


if __name__ == "__main__":
    unittest.main()
