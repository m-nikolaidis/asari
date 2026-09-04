"""Tkinter desktop interface for selected ASARI workflows."""

from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from asari.default_parameters import PARAMETERS

from .gui_adapter import GuiRunRequest, GuiRunResult, run_request, validate_request
from .gui_forms import specs_for_operation


@dataclass
class QueueWriter(io.TextIOBase):
    """Forward worker output to the GUI message queue."""

    messages: queue.Queue

    def write(self, text: str) -> int:
        if text:
            self.messages.put(("log", text))
        return len(text)

    def flush(self) -> None:
        return None


class Application(tk.Tk):
    """Own the single Tk root and all GUI views."""

    def __init__(self) -> None:
        super().__init__()
        self.title("ASARI GUI")
        self.geometry("760x600")
        self.messages: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_requested = False
        self.operation = ""
        self.parameters: dict[str, object] = dict(PARAMETERS)
        self.form_values: dict[str, tk.Variable] = {}
        self.current_frame: ttk.Frame | None = None
        self.show_disclaimer()

    def show_view(self, frame: ttk.Frame) -> None:
        """Replace the current view with one frame."""

        if self.current_frame is not None:
            self.current_frame.destroy()
        self.current_frame = frame
        frame.pack(fill="both", expand=True, padx=24, pady=24)

    def show_disclaimer(self) -> None:
        frame = ttk.Frame(self)
        ttk.Label(
            frame, text="ASARI GUI is Experimental", font=("TkDefaultFont", 16, "bold")
        ).pack(pady=16)
        ttk.Label(
            frame,
            text="This graphical interface is experimental. Use it with caution and report issues to the project.",
            wraplength=560,
            justify="center",
        ).pack(pady=16)
        buttons = ttk.Frame(frame)
        buttons.pack(pady=16)
        ttk.Button(buttons, text="I Accept", command=self.show_operations).pack(
            side="left", padx=8
        )
        ttk.Button(buttons, text="I Decline", command=self.destroy).pack(
            side="left", padx=8
        )
        self.show_view(frame)

    def show_operations(self) -> None:
        frame = ttk.Frame(self)
        ttk.Label(
            frame, text="Choose an operation", font=("TkDefaultFont", 14, "bold")
        ).pack(pady=16)
        for operation in ("process", "analyze", "annotate", "join", "viz"):
            ttk.Button(
                frame,
                text=operation.title(),
                command=lambda name=operation: self.select_operation(name),
            ).pack(fill="x", pady=4)
        self.show_view(frame)

    def select_operation(self, operation: str) -> None:
        self.operation = operation
        self.show_placeholder() if operation == "viz" else self.show_form()

    def show_placeholder(self) -> None:
        frame = ttk.Frame(self)
        ttk.Label(
            frame,
            text="Visualization is not implemented in the GUI yet.",
            wraplength=560,
        ).pack(pady=40)
        ttk.Button(frame, text="Back", command=self.show_operations).pack()
        self.show_view(frame)

    def show_form(self) -> None:
        """Display the fields defined for the selected operation."""

        frame = ttk.Frame(self)
        ttk.Label(
            frame,
            text=f"{self.operation.title()} settings",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(pady=(0, 12))
        fields = ttk.Frame(frame)
        fields.pack(fill="both", expand=True)
        self.form_values = {}
        for row, spec in enumerate(specs_for_operation(self.operation)):
            ttk.Label(fields, text=spec.label).grid(
                row=row, column=0, sticky="w", padx=6, pady=4
            )
            current_value = self.parameters.get(spec.key, spec.default)
            variable = (
                tk.BooleanVar(value=current_value)
                if spec.kind == "boolean"
                else tk.StringVar(value=current_value or "")
            )
            self.form_values[spec.key] = variable
            if spec.kind == "boolean":
                ttk.Checkbutton(fields, variable=variable).grid(
                    row=row, column=1, sticky="w", padx=6, pady=4
                )
            elif spec.kind == "enum":
                ttk.Combobox(
                    fields, textvariable=variable, values=spec.choices, state="readonly"
                ).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            else:
                ttk.Entry(fields, textvariable=variable, width=55).grid(
                    row=row, column=1, sticky="ew", padx=6, pady=4
                )
                if spec.path:
                    is_path_list = spec.key == "input" and self.operation == "join"
                    ttk.Button(
                        fields,
                        text="Path list" if is_path_list else "Browse",
                        command=lambda key=spec.key: self.browse(key),
                    ).grid(row=row, column=2, padx=6, pady=4)
        fields.columnconfigure(1, weight=1)
        buttons = ttk.Frame(frame)
        buttons.pack(pady=12)
        ttk.Button(buttons, text="Back", command=self.show_operations).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="Review", command=self.review_form).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="Run", command=self.run_form).pack(side="left", padx=6)
        self.show_view(frame)

    def browse(self, key: str) -> None:
        """Choose a file or directory for one path field."""

        is_path_list = key == "input" and self.operation == "join"
        chooser = (
            filedialog.askdirectory
            if key == "outdir" or (key == "input" and self.operation == "process")
            else filedialog.askopenfilename
        )
        selected = chooser(
            parent=self,
            title=f"Select {key} path list" if is_path_list else f"Select {key}",
        )
        if selected:
            self.form_values[key].set(selected)

    def review_form(self) -> None:
        self._submit_form(self.show_review)

    def run_form(self) -> None:
        self._submit_form(self.start_request)

    def _submit_form(self, next_action: Callable[[], None]) -> None:
        """Validate current values and continue to the requested action."""

        values = {key: variable.get() for key, variable in self.form_values.items()}
        try:
            self.parameters = validate_request(
                GuiRunRequest(self.operation, {**self.parameters, **values})
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror("Invalid input", str(error), parent=self)
            return
        next_action()

    def show_review(self) -> None:
        """Display validated parameters before execution."""

        frame = ttk.Frame(self)
        ttk.Label(frame, text="Review", font=("TkDefaultFont", 14, "bold")).pack(
            pady=(0, 12)
        )
        summary_frame = ttk.Frame(frame)
        summary_frame.pack(fill="both", expand=True)
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)

        summary = "\n".join(
            f"{key}: {value}"
            for key, value in sorted(self.parameters.items())
            if value not in (None, "")
        )
        summary_text = tk.Text(summary_frame, wrap="word", state="disabled", height=18)
        summary_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            summary_frame, orient="vertical", command=summary_text.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        summary_text.configure(yscrollcommand=scrollbar.set)
        summary_text.configure(state="normal")
        summary_text.insert("1.0", summary)
        summary_text.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(pady=12)
        ttk.Button(buttons, text="Back", command=self.show_form).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="Run", command=self.start_request).pack(
            side="left", padx=6
        )
        self.show_view(frame)

    def start_request(self) -> None:
        """Start an ASARI request in a background worker."""

        self.cancel_requested = False
        self.show_execution()
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(GuiRunRequest(self.operation, dict(self.parameters)),),
            daemon=True,
        )
        self.worker.start()
        self.after(100, self.poll_messages)

    def _run_worker(self, request: GuiRunRequest) -> None:
        """Capture backend output and enqueue the final result."""

        writer = QueueWriter(self.messages)
        try:
            with redirect_stdout(writer), redirect_stderr(writer):
                result = run_request(request)
        except Exception as error:
            result = GuiRunResult(False, None, str(error), error)
        self.messages.put(("result", result))

    def show_execution(self) -> None:
        frame = ttk.Frame(self)
        ttk.Label(
            frame, text=f"Running {self.operation}", font=("TkDefaultFont", 14, "bold")
        ).pack(pady=8)
        self.log_text = tk.Text(frame, height=22, width=85, state="disabled")
        self.log_text.pack(fill="both", expand=True, pady=8)
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=6)
        self.progress.start(10)
        self.cancel_button = ttk.Button(
            frame, text="Cancel", command=self.cancel_request
        )
        self.cancel_button.pack(pady=8)
        self.show_view(frame)

    def poll_messages(self) -> None:
        """Transfer queued worker messages into the active view."""

        # Tkinter widgets must only be updated from this main-thread poll.
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", value)
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                else:
                    self.show_result(value)
                    return
        except queue.Empty:
            if self.worker and self.worker.is_alive():
                self.after(100, self.poll_messages)

    def cancel_request(self) -> None:
        """Record a cooperative cancellation request."""

        # ASARI has no safe interruption hook; report cancellation when it returns.
        self.cancel_requested = True
        self.cancel_button.configure(state="disabled", text="Cancellation requested")
        self.messages.put(
            (
                "log",
                "Cancellation requested; active ASARI work may continue until it returns.\n",
            )
        )

    def show_result(self, result: GuiRunResult) -> None:
        """Display the final request status and output location."""

        self.progress.stop()
        if self.cancel_requested:
            result = GuiRunResult(
                False,
                result.output_directory,
                "Cancellation requested; ASARI work returned.",
                result.error,
            )
        frame = ttk.Frame(self)
        ttk.Label(
            frame,
            text="Completed" if result.succeeded else "Failed",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(pady=12)
        ttk.Label(frame, text=result.message, wraplength=600).pack(pady=8)
        if result.output_directory:
            ttk.Label(
                frame,
                text=f"Output directory:\n{result.output_directory}",
                justify="center",
            ).pack(pady=8)
        ttk.Button(frame, text="Back to operations", command=self.show_operations).pack(
            pady=12
        )
        self.show_view(frame)


def main_gui() -> None:
    """Launch the Tkinter application."""

    Application().mainloop()


if __name__ == "__main__":
    main_gui()
