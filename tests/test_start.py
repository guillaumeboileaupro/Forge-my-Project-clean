import ast
import os
import socket
import stat
import tempfile
import threading
import unittest
from pathlib import Path

import start
from server import Handler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent


def executable(directory, name):
    path = Path(directory) / name
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class InterpreterTests(unittest.TestCase):
    def test_launcher_stays_parsable_by_old_pythons(self):
        # Lance avec un python3 ancien (Anaconda 3.7...) : il doit au moins s'analyser.
        ast.parse((ROOT / "start.py").read_text(encoding="utf-8"), feature_version=(3, 6))

    @unittest.skipIf(os.name == "nt", "executables POSIX")
    def test_first_recent_enough_interpreter_wins(self):
        with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
            executable(old, "python3")
            wanted = executable(new, "python3.12")
            versions = {str(Path(old) / "python3"): (3, 7), wanted: (3, 12)}
            found = start.find_interpreter([old, new], version=lambda p: versions.get(p))
            self.assertEqual(found, wanted)

    @unittest.skipIf(os.name == "nt", "executables POSIX")
    def test_no_recent_interpreter_returns_none(self):
        with tempfile.TemporaryDirectory() as old:
            executable(old, "python3")
            self.assertIsNone(start.find_interpreter([old], version=lambda p: (3, 7)))

    def test_current_interpreter_is_kept_when_recent(self):
        start.ensure_python([])  # aucun exit ni relance sous 3.11+


class PortTests(unittest.TestCase):
    def serve(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_busy_port_is_skipped(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        self.addCleanup(busy.close)
        port = busy.getsockname()[1]
        httpd = start.bind_server(port, 5, lambda address: ThreadingHTTPServer(address, Handler))
        self.addCleanup(httpd.server_close)
        self.assertNotEqual(httpd.server_address[1], port)
        self.assertGreater(httpd.server_address[1], port)

    def test_running_forge_is_recognised(self):
        self.assertTrue(start.forge_running(self.serve()))

    def test_other_service_is_not_taken_for_forge(self):
        other = socket.socket()
        other.bind(("127.0.0.1", 0))
        other.listen()
        self.addCleanup(other.close)
        self.assertFalse(start.forge_running(other.getsockname()[1]))

    def test_non_http_service_is_not_taken_for_forge(self):
        other = socket.socket()
        other.bind(("127.0.0.1", 0))
        other.listen()
        self.addCleanup(other.close)

        def greet():
            conn, _ = other.accept()
            with conn:
                conn.sendall(b"SSH-2.0-OpenSSH_9.6\r\n")
                conn.recv(1024)

        threading.Thread(target=greet, daemon=True).start()
        self.assertFalse(start.forge_running(other.getsockname()[1]))

    def test_invalid_port_is_refused(self):
        with self.assertRaises(SystemExit):
            start.parse_args(["--port", "70000"])


if __name__ == "__main__":
    unittest.main()
