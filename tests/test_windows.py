"""
:File:        tests/test_windows.py

:Details:     Tests for Windows input safety and client launch orchestration.

:Date:        30-10-2026
:Author:      Mick K.
"""

import ctypes
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from qwbot.cli import main, run
from qwbot.controller import Controller
from qwbot.models import Action
from qwbot.windows import Input, Win32Input, WindowsTransport


class WindowsTransportTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.api.foreground.return_value = (123, 456)
        self.api.executable.return_value = "ezquake.exe"
        self.api.emergency_stop.return_value = False
        patcher = patch("qwbot.windows.Win32Input", return_value=self.api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_key_transitions_and_release(self):
        with WindowsTransport() as transport:
            controller = Controller(transport)
            controller.apply(Action(forward=True, jump=True))
            controller.apply(Action(forward=True))
            controller.stop()
        self.assertEqual(
            self.api.key.call_args_list,
            [call(0x11, True), call(0x39, True),
             call(0x39, False), call(0x11, False)],
        )

    def test_focus_loss_releases_keys_without_more_presses(self):
        with self.assertRaisesRegex(RuntimeError, "lost focus"):
            with WindowsTransport() as transport:
                transport.send("+forward")
                self.api.foreground.return_value = (789, 900)
                transport.send("+jump")
        self.assertEqual(self.api.key.call_count, 2)
        self.api.key.assert_called_with(0x11, False)

    def test_emergency_stop_releases_keys(self):
        with self.assertRaisesRegex(RuntimeError, "F12"):
            with WindowsTransport() as transport:
                transport.send("+forward")
                self.api.emergency_stop.return_value = True
                transport.check()
        self.api.key.assert_called_with(0x11, False)

    def test_rotation_calibration(self):
        with WindowsTransport(mouse_counts_per_degree=10) as transport:
            transport.send("rotate -30")
        self.api.mouse.assert_called_once_with(-300)

    def test_rejects_nonfinite_rotation(self):
        with WindowsTransport() as transport:
            with self.assertRaises(ValueError):
                transport.send("rotate nan")
        self.api.mouse.assert_not_called()

    def test_timeout_does_not_send_input_to_other_process(self):
        self.api.executable.return_value = "powershell.exe"
        with self.assertRaisesRegex(RuntimeError, "Focus"):
            with WindowsTransport(timeout=0):
                self.fail("Should not acquire an unrelated window")
        self.api.key.assert_not_called()

    def test_launched_pid_must_match(self):
        with self.assertRaisesRegex(RuntimeError, "Focus"):
            with WindowsTransport(timeout=0, pid=999):
                self.fail("Should not acquire a different client process")
        self.api.key.assert_not_called()

    def test_cleanup_attempts_all_held_keys(self):
        transport = WindowsTransport()
        transport.__enter__()
        transport.send("+forward")
        transport.send("+jump")
        self.api.key.side_effect = OSError("blocked")
        with self.assertRaisesRegex(OSError, "Could not release"):
            transport.__exit__()
        self.assertEqual(self.api.key.call_count, 4)


class LaunchTests(unittest.TestCase):
    def arguments(self, *argv):
        with patch("qwbot.cli.run") as runner:
            main(list(argv))
        return runner.call_args.args[0]

    def test_windows_launch_uses_game_folder_and_startup_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "ezquake.exe"
            executable.touch()
            args = self.arguments(
                "--transport", "windows", "--launch", str(executable),
                "--server", "localhost:27500", "--connect-wait", "0",
            )
            args.duration = 0
            with patch("qwbot.cli.subprocess.Popen") as launch, patch(
                "qwbot.windows.WindowsTransport"
            ) as transport:
                run(args)
            launch.assert_called_once_with(
                [str(executable.resolve()), "+name", "PythonBot01",
                 "+connect", "localhost:27500"],
                cwd=executable.parent,
            )
            self.assertEqual(transport.call_args.args[1], launch.return_value.pid)
            commands = transport.return_value.__enter__.return_value.send.call_args_list
            self.assertTrue(all(call.args[0].startswith("-") for call in commands))

    def test_running_windows_client_requires_manual_connection(self):
        args = self.arguments("--transport", "windows", "--server", "localhost")
        with self.assertRaisesRegex(RuntimeError, "join the server manually"):
            run(args)

    def test_map_is_passed_to_launched_client_on_both_transports(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "ezquake.exe"
            executable.touch()
            for mode in ("windows", "fifo"):
                with self.subTest(transport=mode):
                    args = self.arguments(
                        "--transport", mode, "--launch", str(executable), "--map", "dm6",
                    )
                    args.duration = 0
                    with patch("qwbot.cli.subprocess.Popen") as launch, patch(
                        "qwbot.windows.WindowsTransport"
                    ), patch("qwbot.cli.FIFOTransport"), patch("qwbot.cli.time.sleep") as sleep:
                        run(args)
                    self.assertEqual(launch.call_args.args[0][-2:], ["+map", "dm6"])
                    sleep.assert_called_once_with(args.connect_wait)

    def test_invalid_map_options(self):
        for argv in (
            ["--map", "dm6"],
            ["--launch", "ezquake.exe", "--map", "../dm6"],
            ["--launch", "ezquake.exe", "--map", "dm6;quit"],
            ["--launch", "ezquake.exe", "--map", ""],
            ["--launch", "ezquake.exe", "--map", "dm6", "--server", "localhost"],
        ):
            with self.subTest(argv=argv), patch("sys.stderr"), self.assertRaises(SystemExit):
                main(argv)

    def test_fifo_still_sends_console_commands(self):
        args = self.arguments("--transport", "fifo")
        args.duration = 0
        with patch("qwbot.cli.FIFOTransport") as transport:
            run(args)
        transport.return_value.__enter__.return_value.send.assert_any_call(
            "name PythonBot01"
        )

    def test_run_stops_on_focus_loss_between_action_ticks(self):
        args = self.arguments("--transport", "windows", "--duration", "1")
        api = Mock()
        api.emergency_stop.return_value = False
        api.executable.return_value = "ezquake.exe"
        api.foreground.side_effect = [(123, 456)] * 3 + [(789, 900)]
        with patch("qwbot.windows.Win32Input", return_value=api):
            with self.assertRaisesRegex(RuntimeError, "lost focus"):
                run(args)
        self.assertEqual(api.key.call_args_list, [call(0x11, True), call(0x11, False)])

    def test_invalid_mouse_calibration(self):
        for value in ("nan", "inf", "0", "-1"):
            with self.subTest(value=value), patch("sys.stderr"), self.assertRaises(SystemExit):
                main(["--mouse-counts-per-degree", value])


@unittest.skipUnless(os.name == "nt", "Windows ABI only")
class WindowsAPITests(unittest.TestCase):
    def test_input_structure_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_native_api_loads_and_reads_foreground_without_injecting_input(self):
        api = Win32Input()
        window, pid = api.foreground()
        self.assertIsInstance(pid, int)
        self.assertIsInstance(api.emergency_stop(), bool)


if __name__ == "__main__":
    unittest.main()
