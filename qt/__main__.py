"""Start the Qt version: `py -m qt`, with a copy of the real data unless `--real-data` is given. Packaged, this is
PS Focus itself; `PS Focus.exe --uninstall`, run from Installed apps, opens the uninstall window instead"""

import sys

if "--uninstall" in sys.argv:
    # Handled before anything is opened, so no file the uninstall deletes is in use by this process
    from qt.uninstall_window import main as uninstall

    uninstall()
    sys.exit()

preview = "--real-data" not in sys.argv and not getattr(sys, "frozen", False)
if preview:
    # Before anything imports app_config, which reads the data folder once
    from qt.preview import use_preview_data

    use_preview_data()

from qt.app import main  # noqa: E402

main(preview, smoke_test="--smoke-test" in sys.argv)
