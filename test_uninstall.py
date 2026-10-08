import os
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ui_uninstall
import uninstall


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.environment = {
            "APPDATA": str(self.root / "AppData" / "Roaming"),
            "USERPROFILE": str(self.root),
            "OneDrive": str(self.root / "OneDrive"),
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _directories(self):
        with patch.dict(os.environ, self.environment):
            return uninstall.data_directories()

    def _run_uninstall(self, delete_data):
        with patch.dict(os.environ, self.environment), patch("uninstall.stop_running_app") as stop, patch(
            "uninstall.remove_startup_entries"
        ) as remove_startup, patch("uninstall.remove_program_files") as remove_program_files:
            failed = uninstall.uninstall(delete_data)
        return failed, stop, remove_startup, remove_program_files

    def test_data_directories_cover_settings_history_and_every_backup_folder(self):
        self.assertEqual(
            self._directories(),
            [
                self.root / "AppData" / "Roaming" / "PS Focus",
                self.root / "AppData" / "Roaming" / "FocusTrace",
                self.root / "Documents" / "PS Focus Backups",
                self.root / "OneDrive" / "PS Focus Backups",
            ],
        )

    def test_remove_directories_deletes_data_and_leaves_other_folders_alone(self):
        directories = self._directories()
        for directory in directories[:3]:
            (directory / "backups").mkdir(parents=True)
            (directory / "backups" / "activity-latest.sqlite3").write_bytes(b"history")
        read_only = directories[0] / "settings.json"
        read_only.write_text("{}", encoding="utf-8")
        os.chmod(read_only, stat.S_IREAD)
        unrelated = self.root / "Documents" / "Artwork"
        unrelated.mkdir()

        self.assertEqual(uninstall.remove_directories(directories), [])
        for directory in directories:
            self.assertFalse(directory.exists())
        self.assertTrue(unrelated.exists())

    def test_uninstall_keeps_user_data_by_default(self):
        directories = self._directories()
        directories[0].mkdir(parents=True)
        (directories[0] / "activity.sqlite3").write_bytes(b"history")

        failed, stop, remove_startup, remove_program_files = self._run_uninstall(delete_data=False)

        self.assertEqual(failed, [])
        stop.assert_called_once()
        remove_startup.assert_called_once()
        self.assertEqual((directories[0] / "activity.sqlite3").read_bytes(), b"history")

    def test_uninstall_deletes_user_data_when_requested_but_keeps_program_files_when_run_from_source(self):
        directories = self._directories()
        directories[0].mkdir(parents=True)
        (directories[0] / "activity.sqlite3").write_bytes(b"history")

        failed, stop, remove_startup, remove_program_files = self._run_uninstall(delete_data=True)

        self.assertEqual(failed, [])
        stop.assert_called_once()
        remove_startup.assert_called_once()
        remove_program_files.assert_not_called()
        self.assertFalse(directories[0].exists())

    def test_running_app_is_left_for_the_helper_and_other_files_are_untouched(self):
        running_app = self.root / "PS Focus.exe"
        source_file = self.root / "main.py"
        for path in (running_app, source_file):
            path.write_bytes(b"content")

        with patch("uninstall.subprocess.Popen") as schedule_self_delete:
            self.assertEqual(uninstall.remove_program_files(self.root, running_app), [])

        # Windows cannot delete a running program, so it is left for the helper started here
        self.assertTrue(running_app.exists())
        self.assertTrue(source_file.exists())
        # The path travels in the environment and the command names system programs by their full path
        command = schedule_self_delete.call_args.args[0]
        self.assertNotIn(str(running_app), command)
        self.assertTrue(command.casefold().startswith(f'"{uninstall.system_executable("cmd.exe")}"'.casefold()))
        self.assertEqual(schedule_self_delete.call_args.kwargs["env"][uninstall.SELF_DELETE_VARIABLE], str(running_app))
        self.assertEqual(schedule_self_delete.call_args.kwargs["cwd"], uninstall.system_directory())

    def test_every_file_the_installer_adds_is_removed(self):
        script = (Path(__file__).resolve().parent / "installer" / "PS Focus.iss").read_text(encoding="utf-8")
        installed_names = re.findall(r'DestName: "([^"]+)"', script)
        self.assertTrue(installed_names)
        for name in installed_names:
            self.assertIn(name, uninstall.INSTALLED_FILES)

    def test_installed_copy_removes_its_files_and_empty_folder(self):
        install_directory = self.root / "PS Focus"
        install_directory.mkdir()
        running_app = install_directory / "PS Focus.exe"
        for name in ("PS Focus.exe", *uninstall.INSTALLED_FILES):
            (install_directory / name).write_bytes(b"content")
        self.assertIn("Uninstall PS Focus.exe", uninstall.INSTALLED_FILES)

        with patch("uninstall.subprocess.Popen") as schedule_self_delete:
            self.assertEqual(uninstall.remove_program_files(install_directory, running_app), [])

        self.assertEqual([path.name for path in install_directory.iterdir()], ["PS Focus.exe"])
        environment = schedule_self_delete.call_args.kwargs["env"]
        self.assertEqual(environment[uninstall.INSTALL_DIRECTORY_VARIABLE], str(install_directory))
        command = schedule_self_delete.call_args.args[0]
        self.assertIn(f'rd "%{uninstall.INSTALL_DIRECTORY_VARIABLE}%"', command)
        # The only folder emptied whole is the app's own runtime folder, and only when it is there
        self.assertNotIn(uninstall.RUNTIME_DIRECTORY_VARIABLE, environment)
        self.assertEqual(command.count("/s"), 2)  # cmd's own /s switch, and the runtime folder's rd
        self.assertIn(f'if defined {uninstall.RUNTIME_DIRECTORY_VARIABLE} rd /s /q "%{uninstall.RUNTIME_DIRECTORY_VARIABLE}%"', command)

    def test_installed_runtime_folder_is_removed_after_the_app(self):
        install_directory = self.root / "PS Focus"
        (install_directory / "_internal").mkdir(parents=True)
        running_app = install_directory / "PS Focus.exe"
        running_app.write_bytes(b"content")
        with patch("uninstall.subprocess.Popen") as schedule_self_delete:
            uninstall.remove_program_files(install_directory, running_app)
        environment = schedule_self_delete.call_args.kwargs["env"]
        self.assertEqual(environment[uninstall.RUNTIME_DIRECTORY_VARIABLE], str(install_directory / "_internal"))

    def test_folder_not_named_for_the_app_is_never_removed(self):
        running_app = self.root / "PS Focus.exe"
        running_app.write_bytes(b"content")
        with patch.dict(os.environ, {uninstall.INSTALL_DIRECTORY_VARIABLE: "C:\\Users"}), patch("uninstall.subprocess.Popen") as schedule_self_delete:
            uninstall.remove_program_files(self.root, running_app)

        self.assertNotIn(uninstall.INSTALL_DIRECTORY_VARIABLE, schedule_self_delete.call_args.kwargs["env"])

    def test_runtime_folder_outside_the_apps_own_folder_is_never_removed(self):
        (self.root / "_internal").mkdir()
        running_app = self.root / "PS Focus.exe"
        running_app.write_bytes(b"content")
        with patch.dict(os.environ, {uninstall.RUNTIME_DIRECTORY_VARIABLE: "C:\\Users"}), patch("uninstall.subprocess.Popen") as schedule_self_delete:
            uninstall.remove_program_files(self.root, running_app)
        self.assertNotIn(uninstall.RUNTIME_DIRECTORY_VARIABLE, schedule_self_delete.call_args.kwargs["env"])

    def test_stopping_the_app_spares_the_process_doing_the_uninstall(self):
        with patch("uninstall.subprocess.run") as run, patch("uninstall.time.sleep"), patch("uninstall.os.getpid", return_value=111), patch(
            "uninstall.os.getppid", return_value=222
        ):
            uninstall.stop_running_app()

        command = run.call_args.args[0]
        self.assertEqual(command[1:4], ["/F", "/IM", "PS Focus.exe"])
        self.assertIn("PID ne 111", command)
        self.assertIn("PID ne 222", command)
        # Ending whole process trees would take this process down with its launcher
        self.assertNotIn("/T", command)

    def test_installation_entries_and_shortcuts_are_removed(self):
        programs, desktop = self.root / "Programs", self.root / "Desktop"
        for folder in (programs, desktop):
            folder.mkdir()
            (folder / "PS Focus.lnk").write_bytes(b"shortcut")
        (desktop / "Other.lnk").write_bytes(b"shortcut")
        folders = {uninstall.CSIDL_PROGRAMS: programs, uninstall.CSIDL_DESKTOPDIRECTORY: desktop}
        with patch("uninstall.shell_folder", side_effect=folders.get), patch("winreg.DeleteKey") as delete_key:
            uninstall.remove_installation_entries()

        self.assertEqual(delete_key.call_args.args[1], uninstall.UNINSTALL_KEY_PATH)
        self.assertFalse((programs / "PS Focus.lnk").exists())
        self.assertFalse((desktop / "PS Focus.lnk").exists())
        self.assertTrue((desktop / "Other.lnk").exists())

    def test_keeping_data_uninstalls_without_the_data_warning(self):
        with patch("ui_uninstall.messagebox") as messagebox, patch("ui_uninstall.uninstall", return_value=[]) as run_uninstall:
            self.assertTrue(ui_uninstall.confirm_and_uninstall(False))

        messagebox.askyesno.assert_not_called()
        run_uninstall.assert_called_once_with(False)
        self.assertIn("were kept", messagebox.showinfo.call_args.args[1])

    def test_deleting_data_shows_one_warning_and_stops_when_declined(self):
        parent = Mock()
        with patch("ui_uninstall.messagebox") as messagebox, patch("ui_uninstall.uninstall") as run_uninstall:
            messagebox.askyesno.return_value = False
            self.assertFalse(ui_uninstall.confirm_and_uninstall(True, parent))

        messagebox.askyesno.assert_called_once()
        self.assertEqual(messagebox.askyesno.call_args.args[1], "This will permanently delete all user data. Continue?")
        run_uninstall.assert_not_called()
        parent.withdraw.assert_not_called()

    def test_deleting_data_runs_after_the_warning_is_accepted(self):
        with patch("ui_uninstall.messagebox") as messagebox, patch("ui_uninstall.uninstall", return_value=[]) as run_uninstall:
            messagebox.askyesno.return_value = True
            self.assertTrue(ui_uninstall.confirm_and_uninstall(True))

        messagebox.askyesno.assert_called_once()
        run_uninstall.assert_called_once_with(True)

    def test_uninstaller_opens_its_dialog_without_requesting_admin_rights(self):
        with patch("ui_uninstall.tk.Tk") as create_window, patch("ui_uninstall.UninstallDialog") as dialog:
            ui_uninstall.main()

        dialog.assert_called_once_with(create_window.return_value)
        self.assertFalse(hasattr(uninstall, "relaunch_as_admin"))
        self.assertNotIn("uac_admin", Path(uninstall.__file__).with_name("PS Focus.spec").read_text(encoding="utf-8"))

    def test_app_started_with_the_uninstall_option_only_uninstalls(self):
        import main

        with patch("main.sys.argv", ["PS Focus.exe", "--uninstall"]), patch("main.ui_uninstall.main") as run_uninstaller, patch(
            "main.set_app_user_model_id"
        ) as start_app, patch("main.tk.Tk") as create_window:
            main.main()

        run_uninstaller.assert_called_once_with()
        start_app.assert_not_called()
        create_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
