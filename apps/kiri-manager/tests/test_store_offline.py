"""Desktop Store regression tests without a Qt or Docker installation.

Only the requested GUI methods are loaded from the real application AST;
no desktop, engine, application settings or user data are touched.
"""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


MAIN_SOURCE = Path(__file__).resolve().parents[3] / "DockerControlCenter.py"


def load_method(method_name, globals_map, owner_name="MainWindow"):
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8-sig"))
    owner = next(node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name == owner_name)
    method = next(node for node in owner.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name == method_name)
    namespace = dict(globals_map)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 str(MAIN_SOURCE), "exec"), namespace)
    return namespace[method_name]


class OfflineStoreTest(unittest.TestCase):
    def test_store_opens_without_a_docker_client(self):
        calls = []

        class Dialog:
            def __init__(self, *args, **kwargs):
                calls.append((args, kwargs))

            def exec(self):
                return 0

        open_store = load_method("open_new_container_wizard", {
            "NewContainerDialog": Dialog,
            "QDialog": SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1)),
        })
        host = SimpleNamespace(
            client=None, texts={}, get_llm_settings=lambda: {},
            generate_ai_docker_command=None, build_catalog_image_with_progress=None,
            lang="PL", current_backend="local", remote_arch="",
            wizard_cli_settings=lambda: ("docker", ["docker"]),
            deployment_target_label=lambda: "Local",
        )
        open_store(host)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0][0][0])

    def test_regular_deployment_is_disabled_without_a_client(self):
        warnings = []
        run = load_method("on_run_clicked", {
            "is_manager_template": lambda _: False,
            "QMessageBox": SimpleNamespace(warning=lambda *args: warnings.append(args)),
        }, "NewContainerDialog")
        host = SimpleNamespace(
            client=None, edit_mode=False,
            selected_catalog_template=lambda: None,
            texts={"msg_error": "Error", "docker_not_available": "No Docker connection"},
        )
        run(host)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0][-1], "No Docker connection")

    def test_kiri_action_stays_available_without_docker_desktop(self):
        actions = []
        template = SimpleNamespace(name="DCC Kiri Manager")
        run = load_method("on_run_clicked", {
            "is_manager_template": lambda _: True,
        }, "NewContainerDialog")
        host = SimpleNamespace(
            client=None, edit_mode=False,
            selected_catalog_template=lambda: template,
            on_kiri_store_action=lambda selected: actions.append(selected),
        )
        run(host)
        self.assertEqual(actions, [template])


if __name__ == "__main__":
    unittest.main()
