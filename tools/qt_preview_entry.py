"""Packaged Qt preview entry: always isolate data, including when frozen."""

from qt.preview import use_preview_data
import sys

use_preview_data()

from qt.app import main  # noqa: E402

main(preview=True, smoke_test='--smoke-test' in sys.argv)
