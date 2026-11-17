"""Offline regression tests for clean notebook setup cells."""

import ast
import unittest

from check_environment import clean_notebook_setup


class NotebookSetupTests(unittest.TestCase):
    def test_remove_exact_version_guard_and_unused_metadata_import(self):
        source = 'from importlib.metadata import version\nassert version("agent-framework-core") == "1.17.0", "Select the pinned project kernel."\nfrom agent_framework import Agent\n'
        self.assertEqual(clean_notebook_setup(source), "from agent_framework import Agent\n")

    def test_remove_multiline_kernel_guard_but_keep_behavior_assertion(self):
        source = 'assert Path(sys.executable).resolve() == (repo_root / ".venv/Scripts/python.exe").resolve(), (\n    "Select the repository .venv kernel."\n)\nassert response.text, "No answer"\n'
        self.assertEqual(clean_notebook_setup(source), 'assert response.text, "No answer"\n')

    def test_remove_version_and_kernel_displays(self):
        source = 'from importlib.metadata import version\nprint(f"Kernel: {sys.executable}\\nPython: {sys.version}")\nprint({package: version(package) for package in ("agent-framework-core",)})\nprint("Configuration ready")\n'
        self.assertEqual(clean_notebook_setup(source), 'print("Configuration ready")\n')

    def test_remove_runtime_reporter(self):
        source = 'from scripts.check_environment import report_notebook_runtime\nreport_notebook_runtime()\nendpoint = "example"\n'
        self.assertEqual(clean_notebook_setup(source), 'endpoint = "example"\n')

    def test_functional_sample_code_is_preserved(self):
        source = 'from agent_framework import Agent\n\n\nasync def main():\n    response = await agent.run("Hello")\n    assert response.text\n    print(response.text)\n'
        self.assertEqual(clean_notebook_setup(source), source)
        ast.parse(clean_notebook_setup(source))

    def test_cleanup_is_idempotent(self):
        source = 'print(f"Kernel: {sys.executable}")\n\n\nprint("Ready")\n'
        cleaned = clean_notebook_setup(source)
        self.assertEqual(clean_notebook_setup(cleaned), cleaned)


if __name__ == "__main__":
    unittest.main()