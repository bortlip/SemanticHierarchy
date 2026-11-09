"""Offline tests for the Windows-friendly local server launcher."""

import importlib.util
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

FILE = Path(__file__).resolve().parents[1] / "scripts" / "start.py"
SPEC = importlib.util.spec_from_file_location("semantic_startup", FILE)
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = launcher
SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_root_is_project_root(self):
        self.assertTrue((launcher.ROOT / "web_app.py").is_file())

    def test_free_and_occupied_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            self.assertFalse(launcher.port_is_available(port))
        self.assertTrue(launcher.port_is_available(port))

    def test_exited_server_does_not_open_browser(self):
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "exited"):
            launcher.wait_for_server(process, "http://127.0.0.1:8765")

    def test_no_browser_on_occupied_port(self):
        with (
            patch.object(launcher, "port_is_available", return_value=False),
            patch.object(launcher.subprocess, "Popen") as popen,
            patch.object(launcher.webbrowser, "open") as browser,
        ):
            self.assertEqual(launcher.main(["--port", "8000"]), 2)
            popen.assert_not_called()
            browser.assert_not_called()

    def test_success_opens_page_after_readiness(self):
        process = Mock()
        process.wait.return_value = 0
        process.returncode = 0
        process.poll.return_value = 0
        with (
            patch.object(launcher, "port_is_available", return_value=True),
            patch.object(launcher.subprocess, "Popen", return_value=process),
            patch.object(launcher, "wait_for_server") as wait_ready,
            patch.object(launcher.webbrowser, "open", return_value=True) as browser,
        ):
            self.assertEqual(launcher.main(["--port", "8765"]), 0)
            wait_ready.assert_called_once()
            browser.assert_called_once_with("http://127.0.0.1:8765")
            process.wait.assert_called_once()

    def test_no_browser_flag(self):
        process = Mock()
        process.wait.return_value = 0
        process.returncode = 0
        process.poll.return_value = 0
        with (
            patch.object(launcher, "port_is_available", return_value=True),
            patch.object(launcher.subprocess, "Popen", return_value=process),
            patch.object(launcher, "wait_for_server"),
            patch.object(launcher.webbrowser, "open") as browser,
        ):
            self.assertEqual(launcher.main(["--port", "8765", "--no-browser"]), 0)
            browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
