from types import SimpleNamespace
from pathlib import Path
import os
import inspect
import unittest
from unittest.mock import patch

from asari.tools.gui_adapter import (
    GuiRunRequest,
    build_args,
    normalize_paths,
    validate_request,
)
from asari.tools.gui_forms import specs_for_operation, validate_form_values


class TestGuiAdapter(unittest.TestCase):
    def test_normalize_paths_expands_user_paths(self):
        original = os.environ.get("GUI_TEST_INPUT")
        os.environ["GUI_TEST_INPUT"] = "/tmp"
        try:
            result = normalize_paths({"input": "$GUI_TEST_INPUT/sample.mzML"})
        finally:
            if original is None:
                os.environ.pop("GUI_TEST_INPUT", None)
            else:
                os.environ["GUI_TEST_INPUT"] = original
        self.assertEqual(result["input"], str(Path("/tmp/sample.mzML").resolve()))

    def test_validate_request_rejects_missing_process_input(self):
        with self.assertRaisesRegex(ValueError, "input"):
            validate_request(GuiRunRequest("process", {"input": ""}))

    def test_validate_request_rejects_invalid_enum(self):
        with self.assertRaisesRegex(ValueError, "mode"):
            validate_request(
                GuiRunRequest("process", {"input": "/tmp", "mode": "bad"})
            )

    def test_build_args_supplies_handler_attributes(self):
        args = build_args({"input": "/tmp/input", "min_peak_height": 12})
        self.assertIsInstance(args, SimpleNamespace)
        self.assertEqual(args.input, "/tmp/input")
        self.assertEqual(args.min_peak_height, 12)
        self.assertIsNone(args.table_for_viz)

    def test_process_form_hides_viz_only_parameter(self):
        self.assertNotIn("table_for_viz", {spec.key for spec in specs_for_operation("process")})

    def test_form_validation_coerces_numeric_values(self):
        values = validate_form_values("process", {"input": "/tmp", "multicores": "2"})
        self.assertEqual(values["multicores"], 2)

    @patch("asari.main.update_peak_detection_params", side_effect=lambda values, args: values)
    @patch("asari.main.run_asari")
    def test_run_request_reports_backend_success(self, run_asari, _update):
        from asari.tools.gui_adapter import run_request

        result = run_request(GuiRunRequest("process", {"input": "/tmp", "outdir": "/tmp/out"}))
        self.assertTrue(result.succeeded)
        self.assertEqual(result.output_directory, str(Path("/tmp/out").resolve()))
        run_asari.assert_called_once()

    def test_run_request_reports_viz_placeholder(self):
        from asari.tools.gui_adapter import run_request

        result = run_request(GuiRunRequest("viz", {"input": "/tmp/project"}))
        self.assertFalse(result.succeeded)
        self.assertIn("not implemented", result.message)
    def test_review_view_keeps_actions_outside_scrollable_summary(self):
        from asari.tools.gui import Application

        review_source = inspect.getsource(Application.show_review)
        self.assertIn('summary_text = tk.Text(summary_frame', review_source)
        self.assertIn("scrollbar = ttk.Scrollbar(", review_source)
        self.assertIn("summary_frame, orient=\"vertical\"", review_source)
        self.assertIn('summary_frame.pack(fill="both", expand=True)', review_source)
        self.assertIn('buttons.pack(pady=12)', review_source)
        self.assertIn('text="Back", command=self.show_form', review_source)
        self.assertIn('text="Run", command=self.start_request', review_source)

    def test_direct_run_validates_parameters_before_starting(self):
        from asari.tools.gui import Application

        class FormValue:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        application = Application.__new__(Application)
        application.operation = "process"
        application.parameters = {}
        application.form_values = {
            "input": FormValue("/tmp/input"),
            "multicores": FormValue("2"),
        }
        started = []
        application.start_request = lambda: started.append(True)

        application.run_form()

        self.assertEqual(application.parameters["input"], str(Path("/tmp/input").resolve()))
        self.assertEqual(application.parameters["multicores"], 2)
        self.assertEqual(started, [True])

    def test_form_restores_validated_boolean_values(self):
        from asari.tools import gui

        spec = SimpleNamespace(
            key="autoheight",
            label="Estimate peak height",
            kind="boolean",
            default=False,
            path=False,
        )
        application = gui.Application.__new__(gui.Application)
        application.operation = "process"
        application.parameters = {"autoheight": True}
        application.current_frame = None

        with (
            patch.object(gui, "specs_for_operation", return_value=(spec,)),
            patch.object(gui.ttk, "Frame"),
            patch.object(gui.ttk, "Label"),
            patch.object(gui.ttk, "Checkbutton"),
            patch.object(gui.ttk, "Button"),
            patch.object(
                gui.tk,
                "BooleanVar",
                side_effect=lambda *, value: SimpleNamespace(value=value),
            ),
        ):
            application.show_form()

        self.assertIs(application.form_values["autoheight"].value, True)

    @patch("asari.tools.gui.filedialog.askopenfilename", return_value="/tmp/paths.txt")
    def test_join_input_browser_selects_a_path_list(self, askopenfilename):
        from asari.tools.gui import Application

        selected = []
        application = Application.__new__(Application)
        application.operation = "join"
        application.form_values = {
            "input": SimpleNamespace(set=selected.append),
        }

        application.browse("input")

        askopenfilename.assert_called_once_with(
            parent=application, title="Select input path list"
        )
        self.assertEqual(selected, ["/tmp/paths.txt"])
