"""WhisperX dictation: core library and optional GUI."""

__all__ = ["cli_main", "gui_main"]


def __getattr__(name):
    if name == "cli_main":
        from whisperx_dictate.cli import cli_main as _cli_main

        return _cli_main
    if name == "gui_main":
        from whisperx_dictate.gui_app import gui_main as _gui_main

        return _gui_main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
