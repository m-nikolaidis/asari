"""Metadata and Tkinter form helpers for the ASARI GUI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterSpec:
    """Describe how one ASARI parameter is displayed and validated."""

    key: str
    label: str
    kind: str
    default: object = None
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    operations: tuple[str, ...] = ()
    required: bool = False
    path: bool = False


PARAMETER_SPECS = (
    ParameterSpec("input", "Input", "path", required=True, path=True),
    ParameterSpec("outdir", "Output directory", "path", path=True),
    ParameterSpec("project_name", "Project name", "string"),
    ParameterSpec("mode", "Ionization mode", "enum", "pos", ("pos", "neg"), operations=("process",)),
    ParameterSpec("workflow", "Workflow", "enum", "LC", ("LC", "GC", "DIMS", "LCMSMS")),
    ParameterSpec("multicores", "CPU cores", "integer", 4, minimum=1),
    ParameterSpec("mz_tolerance_ppm", "m/z tolerance (ppm)", "float", 5.0, minimum=0),
    ParameterSpec("min_peak_height", "Minimum peak height", "float", 100000.0, minimum=0),
    ParameterSpec("autoheight", "Estimate peak height", "boolean", False),
    ParameterSpec("reference", "Reference file", "path", path=True),
    ParameterSpec("database", "Annotation database", "path", path=True, operations=("annotate",)),
    ParameterSpec("kovats", "Kovats index file", "path", path=True, operations=("annotate",)),
    ParameterSpec("denovo", "De novo annotation", "boolean", False, operations=("annotate",)),
    ParameterSpec("table_for_viz", "Visualization table", "enum", "preferred", ("preferred", "full"), operations=("viz",)),
)


def specs_for_operation(operation: str) -> tuple[ParameterSpec, ...]:
    """Return form fields relevant to an operation."""

    return tuple(
        spec
        for spec in PARAMETER_SPECS
        if not spec.operations or operation in spec.operations
    )


def coerce_value(spec: ParameterSpec, value: object) -> object:
    """Convert and validate one raw form value."""

    if spec.kind == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "1", "yes", "on"}:
            return True
        if str(value).lower() in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"{spec.label} must be a boolean")
    if spec.kind == "integer":
        converted = int(value)
    elif spec.kind == "float":
        converted = float(value)
    elif spec.kind == "enum":
        converted = str(value)
        if converted not in spec.choices:
            raise ValueError(f"{spec.label} must be one of: {', '.join(spec.choices)}")
    else:
        converted = "" if value is None else str(value)
    if spec.minimum is not None and converted < spec.minimum:
        raise ValueError(f"{spec.label} must be at least {spec.minimum}")
    if spec.required and not converted:
        raise ValueError(f"{spec.key}: {spec.label} is required")
    return converted


def validate_form_values(operation: str, values: dict[str, object]) -> dict[str, object]:
    """Return copied form values after operation-specific validation."""

    specs = {spec.key: spec for spec in specs_for_operation(operation)}
    result = dict(values)
    for key, spec in specs.items():
        if key in values:
            result[key] = coerce_value(spec, values[key])
        elif spec.required:
            raise ValueError(f"{spec.key}: {spec.label} is required")
    return result
