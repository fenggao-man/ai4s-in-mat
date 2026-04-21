import tempfile
import unittest
from pathlib import Path

from main import find_latest_ocr_run


class MainManualTestCase(unittest.TestCase):
    def test_find_latest_ocr_run_returns_latest_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc_dir = root / "助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响"
            older = doc_dir / "run_20260331_042800"
            newer = doc_dir / "run_20260401_010203"
            older.mkdir(parents=True)
            newer.mkdir(parents=True)

            result = find_latest_ocr_run(
                artifacts_root=root,
                doc_slug="助剂对Ru_CeO2催化剂的表面性质及氨合成性能的影响",
            )

            self.assertEqual(result, newer)


if __name__ == "__main__":
    unittest.main()
