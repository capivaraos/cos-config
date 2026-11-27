import os
import unittest
from unittest import mock

from cos_config import preload

LIB = preload.LIBRARY


class WantsPreloadTest(unittest.TestCase):
    def test_wayland_sessions(self):
        self.assertTrue(preload.wants_preload({"WAYLAND_DISPLAY": "wayland-0"}))
        self.assertTrue(preload.wants_preload({"XDG_SESSION_TYPE": "wayland"}))

    def test_x11_and_no_session(self):
        self.assertFalse(preload.wants_preload({"XDG_SESSION_TYPE": "x11"}))
        self.assertFalse(preload.wants_preload({}))

    def test_not_twice(self):
        wayland = {"WAYLAND_DISPLAY": "wayland-0"}
        self.assertFalse(preload.wants_preload(preload.preload_env(wayland)))
        self.assertFalse(preload.wants_preload(dict(wayland, LD_PRELOAD=LIB)))


class EnvTest(unittest.TestCase):
    def test_library_goes_first_and_others_are_kept(self):
        env = preload.preload_env({"LD_PRELOAD": "libother.so", "HOME": "/root"})
        self.assertEqual(env["LD_PRELOAD"], f"{LIB} libother.so")
        self.assertEqual(env[preload.MARKER], "1")
        self.assertEqual(env["HOME"], "/root")

    def test_round_trip_restores_the_environment(self):
        for original in ({"HOME": "/root"}, {"HOME": "/root", "LD_PRELOAD": "libother.so"}):
            self.assertEqual(preload.restored_env(preload.preload_env(original)), original)


class EnsureTest(unittest.TestCase):
    WAYLAND = {"XDG_SESSION_TYPE": "wayland", "HOME": "/root"}

    def run_ensure(self, environ, available=True, execve=None):
        with mock.patch.dict(os.environ, environ, clear=True), \
                mock.patch.object(preload, "available", return_value=available), \
                mock.patch.object(preload.os, "execve", execve or mock.Mock()) as ex, \
                mock.patch.object(preload.sys, "argv", ["/usr/bin/cos-config", "--x"]):
            preload.ensure()
            return ex, dict(os.environ)

    def test_restarts_once_with_the_library_preloaded(self):
        ex, _env = self.run_ensure(self.WAYLAND)
        path, argv, env = ex.call_args.args
        self.assertEqual(argv[1:], ["/usr/bin/cos-config", "--x"])
        self.assertEqual(env["LD_PRELOAD"], LIB)
        self.assertEqual(env[preload.MARKER], "1")

    def test_restarted_process_cleans_its_environment(self):
        ex, env = self.run_ensure(preload.preload_env(self.WAYLAND))
        ex.assert_not_called()
        self.assertEqual(env, self.WAYLAND)

    def test_no_restart_without_the_library(self):
        ex, env = self.run_ensure(self.WAYLAND, available=False)
        ex.assert_not_called()
        self.assertEqual(env, self.WAYLAND)

    def test_exec_failure_starts_without_it(self):
        ex, env = self.run_ensure(self.WAYLAND, execve=mock.Mock(side_effect=OSError))
        ex.assert_called_once()
        self.assertEqual(env, self.WAYLAND)


if __name__ == "__main__":
    unittest.main()
