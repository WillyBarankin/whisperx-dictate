"""CLI entry: argument parsing and main dictation loop."""

import argparse
import os
import platform
import time

from pynput import keyboard

from whisperx_dictate.cli_apps import CLIApp, CLIAppEnter
from whisperx_dictate.devices import print_input_devices
from whisperx_dictate.hotkeys import DoubleCommandKeyListener, GlobalKeyListener
from whisperx_dictate.runtime import build_recorder, build_transcriber, prepare_glossary_and_prompt
from whisperx_dictate.server import run_server


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Dictation app using WhisperX (faster-whisper) ASR. By default the keyboard shortcut cmd+option '
        '(macOS) or ctrl+alt (others) starts and stops dictation.')
    parser.add_argument('-m', '--model_name', type=str,
                        choices=['tiny', 'tiny.en', 'base', 'base.en', 'small', 'small.en', 'medium', 'medium.en', 'large', 'large-v2', 'large-v3'],
                        default='base',
                        help='See GitHub whisper model list. Default: base.')
    parser.add_argument('-k', '--key_combination', type=str,
                        default='cmd_l+alt' if platform.system() == 'Darwin' else 'ctrl+space',
                        help='Hotkey to start/stop recording.')
    parser.add_argument('--k_double_cmd', action='store_true',
                        help='macOS: double Right Command to toggle.')
    parser.add_argument('-l', '--language', type=str, default=None,
                        help='Language code(s), comma-separated.')
    parser.add_argument('-t', '--max_time', type=float, default=None,
                        help='Optional max recording duration in seconds.')
    parser.add_argument('--enter-to-toggle', action='store_true',
                        help='Use Enter in the terminal to toggle recording.')
    parser.add_argument('--save-dir', type=str, default=None, metavar='DIR',
                        help='Directory for saved notes.')
    parser.add_argument('--save-naming', type=str, choices=['number', 'time'], default='number',
                        help='Save file naming: number or time.')
    parser.add_argument('--save-hotkey', type=str, default='ctrl+alt+n', metavar='KEYS',
                        help='Hotkey to save last transcription.')
    parser.add_argument('--save-stop-hotkey', type=str, default='ctrl+alt+space', metavar='KEYS',
                        help='Stop recording and save to file.')
    parser.add_argument('--server', action='store_true',
                        help='Run HTTP API server instead of dictation UI.')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Server bind address (with --server).')
    parser.add_argument('--port', type=int, default=8765,
                        help='Server port (with --server).')
    parser.add_argument('--server-url', type=str, default=None, metavar='URL',
                        help='Remote server URL for transcription (no local model).')
    parser.add_argument('--input-devices', type=str, default=None, metavar='IDS',
                        help='Comma-separated device indices.')
    parser.add_argument('--list-devices', action='store_true',
                        help='List audio devices and exit.')
    parser.add_argument('--diarize', action='store_true',
                        help='Speaker diarization.')
    parser.add_argument('--diarize-model', type=str, default='pyannote/speaker-diarization-community-1',
                        help='Diarization model name.')
    parser.add_argument('--hf-token', type=str, default=None,
                        help='Hugging Face token for diarization.')
    parser.add_argument('--initial-prompt', type=str, default=None, metavar='TEXT',
                        help='ASR initial_prompt text.')
    parser.add_argument('--initial-prompt-file', type=str, default=None, metavar='PATH',
                        help='File for initial_prompt.')
    parser.add_argument('--glossary-file', type=str, default=None, metavar='PATH',
                        help='Glossary TSV path.')
    parser.add_argument('--no-glossary-prompt', action='store_true',
                        help='Glossary: replacements only, no auto initial_prompt.')
    parser.add_argument('--translate', action='store_true',
                        help='Whisper task=translate: output English text from speech in any language. '
                        'Default is transcribe (keep spoken language). Use a multilingual model, not *.en.')
    parser.add_argument('--api-token', type=str, default=None, metavar='TOKEN',
                        help='Bearer token for server or client.')
    parser.add_argument(
        '--inject-type-delay-ms',
        type=float,
        default=None,
        metavar='MS',
        dest='inject_type_delay_ms',
        help='Uniform delay between injected keystrokes (ms). Ignored if --inject-type-custom-delays. '
        'Otherwise omit for built-in default (2.5 ms per char) or WHISPERX_DICTATE_INJECT_DELAY_MS.',
    )
    parser.add_argument(
        '--inject-type-custom-delays',
        action='store_true',
        dest='inject_type_use_custom_delays',
        help='Use separate delays for characters and for extra pause after each space (see next two flags).',
    )
    parser.add_argument(
        '--inject-type-char-ms',
        type=float,
        default=45.0,
        dest='inject_type_char_delay_ms',
        metavar='MS',
        help='With --inject-type-custom-delays: pause after each character (ms). Default: 45.',
    )
    parser.add_argument(
        '--inject-type-space-extra-ms',
        type=float,
        default=55.0,
        dest='inject_type_space_extra_ms',
        metavar='MS',
        help='With --inject-type-custom-delays: extra pause after each space (ms). Default: 55.',
    )

    args = parser.parse_args(args=argv)

    if not args.api_token:
        args.api_token = os.environ.get("WHISPERX_API_TOKEN") or None

    if args.language is not None:
        args.language = args.language.split(',')

    if args.model_name.endswith('.en') and args.language is not None and any(lang != 'en' for lang in args.language):
        raise ValueError('If using a model ending in .en, you cannot specify a language other than English.')
    if args.input_devices is not None:
        try:
            args.input_devices = [int(x.strip()) for x in args.input_devices.split(",") if x.strip()]
        except ValueError as e:
            raise ValueError("Invalid --input-devices format. Use comma-separated integer indices, e.g. 1,3") from e
    if args.initial_prompt and args.initial_prompt_file:
        raise ValueError("Use either --initial-prompt or --initial-prompt-file, not both.")
    if args.glossary_file and not os.path.isfile(args.glossary_file):
        raise ValueError("Glossary file not found: {}".format(args.glossary_file))
    if args.inject_type_delay_ms is not None and args.inject_type_delay_ms <= 0:
        raise ValueError("--inject-type-delay-ms must be a positive number.")
    if args.inject_type_use_custom_delays:
        if args.inject_type_char_delay_ms < 0 or args.inject_type_space_extra_ms < 0:
            raise ValueError("--inject-type-char-ms and --inject-type-space-extra-ms must be >= 0.")
    return args


def cli_main(argv=None):
    args = parse_args(argv)

    if getattr(args, "list_devices", False):
        print_input_devices()
        raise SystemExit(0)

    glossary_pairs, initial_prompt, user_prompt, auto_from_glossary = prepare_glossary_and_prompt(args)
    transcriber = build_transcriber(
        args, glossary_pairs, initial_prompt, user_prompt, auto_from_glossary,
    )
    recorder = build_recorder(transcriber, args)

    if getattr(args, "server", False):
        if getattr(args, "server_url", None):
            print("Cannot use --server and --server-url together.")
            raise SystemExit(1)
        lang = args.language[0] if args.language else None
        run_server(
            transcriber,
            args.host,
            args.port,
            language=lang,
            api_token=getattr(args, "api_token", None),
        )
        raise SystemExit(0)

    if getattr(args, "enter_to_toggle", False):
        app = CLIAppEnter(recorder, args.language, args.max_time)
        print("Enter-to-toggle: press Enter to start recording, Enter again to stop. Result is printed and copied to clipboard.")
        if (getattr(args, "save_dir", None) or getattr(args, "server_url", None)) and platform.system() == "Windows":
            try:
                import keyboard as kb
                from whisperx_dictate.win_keyboard_hooks import hotkey_registration_layout_fix

                save_hk = getattr(args, "save_hotkey", "ctrl+alt+n").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                save_stop_hk = getattr(args, "save_stop_hotkey", "ctrl+alt+space").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
                with hotkey_registration_layout_fix():
                    kb.add_hotkey(save_hk, app.save_last_note, suppress=False)
                    kb.add_hotkey(save_stop_hk, app.stop_and_save, suppress=False)
                transcriber.save_note_hint = save_hk
                print("Stop recording + save to file: {}".format(save_stop_hk))
            except Exception:
                pass
        app.run()
        return

    app = CLIApp(recorder, args.language, args.max_time)
    key_combo = args.key_combination
    use_keyboard_lib = False
    if platform.system() == "Windows":
        try:
            import keyboard as kb
            from whisperx_dictate.win_keyboard_hooks import hotkey_registration_layout_fix

            hotkey_str = key_combo.replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
            if hotkey_str in ("ctrl+alt", "control+alt"):
                hotkey_str = "ctrl+alt+space"
            save_hk = getattr(args, "save_hotkey", "ctrl+alt+n").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
            save_stop_hk = getattr(args, "save_stop_hotkey", "ctrl+alt+space").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
            with hotkey_registration_layout_fix():
                kb.add_hotkey(hotkey_str, app.toggle, suppress=False)
                if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
                    kb.add_hotkey(save_hk, app.save_last_note, suppress=False)
                    kb.add_hotkey(save_stop_hk, app.stop_and_save, suppress=False)
            if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
                transcriber.save_note_hint = save_hk
            use_keyboard_lib = True
            key_combo = hotkey_str
        except ImportError:
            pass
        except Exception as e:
            print("(keyboard lib failed:", e, "- using pynput)")

    if use_keyboard_lib:
        print("Running... (hotkey: {} — press Ctrl+C to quit)".format(key_combo))
        if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
            save_stop_hk = getattr(args, "save_stop_hotkey", "ctrl+alt+space").replace("_l", "").replace("_r", "").replace("cmd", "win").replace("command", "win").lower()
            print("Stop recording + save to file: {}".format(save_stop_hk))
        print("If hotkey does not work, run this terminal as Administrator or use --enter-to-toggle.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nQuit.")
        return

    if args.k_double_cmd:
        key_listener = DoubleCommandKeyListener(app)
    else:
        key_listener = GlobalKeyListener(app, key_combo)
    listener = keyboard.Listener(on_press=key_listener.on_key_press, on_release=key_listener.on_key_release)
    listener.start()
    print("Running... (hotkey: {})".format(key_combo))
    if getattr(args, "save_dir", None) or getattr(args, "server_url", None):
        save_stop_combo = getattr(args, "save_stop_hotkey", "ctrl+alt+space")
        save_stop_listener_obj = GlobalKeyListener(app, save_stop_combo)
        save_stop_listener_obj.app = type("_ShimApp", (), {"toggle": app.stop_and_save})()
        save_stop_listener = keyboard.Listener(
            on_press=save_stop_listener_obj.on_key_press,
            on_release=save_stop_listener_obj.on_key_release,
        )
        save_stop_listener.start()
        print("Stop recording + save to file: {}".format(save_stop_combo))
    app.run()


def main():
    """Alias for cli_main (tools may expect `main`)."""
    cli_main()


if __name__ == "__main__":
    cli_main()
