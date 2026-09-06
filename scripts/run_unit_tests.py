"""Run foundation tests and reject an empty discovery result."""

from pathlib import Path
import unittest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(root / "tests/unit"))
    if suite.countTestCases() == 0:
        print("No foundation tests discovered; refusing a false green.")
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return not result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(main())
