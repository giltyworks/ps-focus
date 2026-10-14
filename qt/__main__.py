"""Start the Qt version: `py -m qt`, with a copy of the real data unless `--real-data` is given. Packaged, this is
PS Focus itself; `PS Focus.exe --uninstall`, run from Installed apps, opens the uninstall window instead, and
`PS Focus.exe --dev` the developer version: a copy of the data with a menu of things to try, see dev_tools"""

import sys

if "--uninstall" in sys.argv:
    # Handled before anything is opened, so no file the uninstall deletes is in use by this process
    from qt.uninstall_window import main as uninstall

    uninstall()
    sys.exit()

dev = "--dev" in sys.argv
data_copy = dev or ("--real-data" not in sys.argv and not getattr(sys, "frozen", False))
if data_copy:
    # Before anything imports app_config, which reads the data folder once
    from qt.data_copy import COPY_FOLDER_NAME, DEV_FOLDER_NAME, use_data_copy

    use_data_copy(DEV_FOLDER_NAME if dev else COPY_FOLDER_NAME)

from qt.app import main  # noqa: E402

main(data_copy, smoke_test="--smoke-test" in sys.argv, dev=dev)
