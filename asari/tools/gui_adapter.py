"""Testable bridge between the Tkinter GUI and ASARI's command runner."""

from dataclasses import dataclass
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

from .gui_forms import validate_form_values


SUPPORTED_OPERATIONS = ("process", "analyze", "annotate", "join", "viz")
PATH_KEYS = {
    "input",
    "files",
    "reference",
    "outdir",
    "database",
    "kovats",
    "sample_metadata",
    "reuse_intermediates",
}
ARGS_KEYS = (
    "input",
    "table_for_viz",
    "min_peak_height",
    "min_prominence_threshold",
    "cal_min_peak_height",
    "min_intensity_threshold",
)


@dataclass(frozen=True)
class GuiRunRequest:
    """Describe one operation requested by the GUI."""

    operation: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class GuiRunResult:
    """Describe the outcome returned to the GUI."""

    succeeded: bool
    output_directory: str | None
    message: str
    error: Exception | None = None


def _absolute_path(value: object) -> str:
    return str(Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve())


def normalize_paths(parameters: Mapping[str, object]) -> dict[str, object]:
    """Return copied parameters with user paths made absolute."""

    normalized = dict(parameters)
    for key in PATH_KEYS:
        value = normalized.get(key)
        if isinstance(value, (str, Path)) and str(value):
            normalized[key] = _absolute_path(value)
        elif isinstance(value, (list, tuple)):
            normalized[key] = [_absolute_path(item) for item in value if str(item)]
    return normalized


def validate_request(request: GuiRunRequest) -> dict[str, object]:
    """Validate and normalize parameters for one GUI request."""

    if request.operation not in SUPPORTED_OPERATIONS:
        raise ValueError(f"Unsupported operation: {request.operation}")
    if request.operation == "viz":
        return normalize_paths(request.parameters)

    parameters = normalize_paths(request.parameters)
    parameters = validate_form_values(request.operation, parameters)
    if request.operation == "analyze" and not str(parameters["input"]).lower().endswith(".mzml"):
        raise ValueError("analyze input must be an .mzML file")
    return parameters


def build_args(parameters: Mapping[str, object]) -> SimpleNamespace:
    """Build the argument attributes expected by ASARI handlers."""

    return SimpleNamespace(**{key: parameters.get(key) for key in ARGS_KEYS})


def run_request(request: GuiRunRequest) -> GuiRunResult:
    """Run one request and return backend failures as result data."""

    try:
        parameters = validate_request(request)
        if request.operation == "viz":
            return GuiRunResult(False, None, "Visualization is not implemented in the GUI.")

        from asari.main import run_asari, update_peak_detection_params

        parameters["run"] = request.operation
        parameters = update_peak_detection_params(parameters, build_args(parameters))
        run_asari(parameters, build_args(parameters))
        output_directory = parameters.get("outdir")
        return GuiRunResult(
            True,
            str(output_directory) if output_directory else None,
            f"{request.operation} completed successfully.",
        )
    except Exception as error:
        return GuiRunResult(False, None, str(error) or error.__class__.__name__, error)
