"""
Unit tests for env.py's isolation guarantees. No qelectrotech binary
needed -- these check the sandbox structure itself, not what runs in it.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from simulator import env


class TestSandbox(unittest.TestCase):
    def test_sandbox_has_isolated_home_and_xdg(self):
        sb = env.make_sandbox()
        try:
            self.assertTrue(str(sb.home).startswith(str(sb.root)))
            self.assertTrue(str(sb.config_home).startswith(str(sb.root)))
            self.assertTrue(str(sb.data_home).startswith(str(sb.root)))
            e = sb.child_env()
            self.assertEqual(e["HOME"], str(sb.home))
            self.assertEqual(e["XDG_CONFIG_HOME"], str(sb.config_home))
            self.assertEqual(e["XDG_DATA_HOME"], str(sb.data_home))
        finally:
            sb.cleanup()

    def test_sandbox_forces_offscreen_platform(self):
        sb = env.make_sandbox()
        try:
            self.assertEqual(sb.child_env()["QT_QPA_PLATFORM"], "offscreen")
        finally:
            sb.cleanup()

    def test_sandbox_clears_display_variables(self):
        # A stray DISPLAY/WAYLAND_DISPLAY reaching a sandboxed run is
        # exactly the kind of leak that has silently produced wrong-binary
        # results in this project's history (see env.py's module docstring).
        sb = env.make_sandbox()
        try:
            e = sb.child_env()
            self.assertEqual(e["DISPLAY"], "")
            self.assertEqual(e["WAYLAND_DISPLAY"], "")
        finally:
            sb.cleanup()

    def test_two_sandboxes_are_independent(self):
        sb1 = env.make_sandbox()
        sb2 = env.make_sandbox()
        try:
            self.assertNotEqual(sb1.root, sb2.root)
            self.assertNotEqual(sb1.home, sb2.home)
        finally:
            sb1.cleanup()
            sb2.cleanup()

    def test_cleanup_removes_the_sandbox_directory(self):
        sb = env.make_sandbox()
        root = sb.root
        self.assertTrue(root.exists())
        sb.cleanup()
        self.assertFalse(root.exists())

    def test_context_manager_cleans_up_on_success(self):
        with env.sandbox_context() as sb:
            root = sb.root
            self.assertTrue(root.exists())
        self.assertFalse(root.exists())

    def test_context_manager_cleans_up_on_exception(self):
        root = None
        with self.assertRaises(ValueError):
            with env.sandbox_context() as sb:
                root = sb.root
                raise ValueError("boom")
        self.assertFalse(root.exists())

    def test_context_manager_keep_on_error_preserves_sandbox(self):
        root = None
        with self.assertRaises(ValueError):
            with env.sandbox_context(keep_on_error=True) as sb:
                root = sb.root
                raise ValueError("boom")
        self.assertTrue(root.exists())
        # Clean up manually since the test asked for preservation.
        import shutil
        shutil.rmtree(root, ignore_errors=True)


class TestLivenessGuard(unittest.TestCase):
    def test_no_such_process_name_does_not_raise(self):
        # Extremely unlikely to collide with a real running process.
        env.assert_no_other_qet_running("definitely-not-a-real-binary-name-xyz123")


if __name__ == "__main__":
    unittest.main()
