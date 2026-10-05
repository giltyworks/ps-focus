"""Start the Qt version: `py -m qt`, with a copy of the real data unless `--real-data` is given"""

import sys

preview = "--real-data" not in sys.argv and not getattr(sys, "frozen", False)
if preview:
    # Before anything imports app_config, which reads the data folder once
    from qt.preview import use_preview_data

    use_preview_data()

from qt.app import main  # noqa: E402

main(preview)
