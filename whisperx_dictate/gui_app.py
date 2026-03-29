"""Tkinter GUI for WhisperX Dictate."""

import json
import os
import queue
import threading
from types import SimpleNamespace

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from whisperx_dictate.devices import list_input_devices
from whisperx_dictate.runtime import build_recorder, build_transcriber, prepare_glossary_and_prompt
from whisperx_dictate.server import run_server_in_thread
from whisperx_dictate import app_icon, tray_support
from whisperx_dictate.win_gui_console import apply_gui_console_preference
from whisperx_dictate.win_keyboard_hooks import hotkey_registration_layout_fix


def _release_transcriber_resources(transcriber) -> None:
    """Drop heavy model references before loading another (GPU RAM)."""
    if transcriber is None:
        return
    try:
        transcriber._diarization_pipeline = None
    except Exception:
        pass
    try:
        if getattr(transcriber, "model", None) is not None:
            transcriber.model = None
    except Exception:
        pass
    try:
        import gc

        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def gui_config_path():
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        d = os.path.join(base, "WhisperXDictate")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "whisperx-dictate")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "gui_config.json")


MODELS = [
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large", "large-v2", "large-v3",
]

DEFAULT_CONFIG = {
    "language": "ru",
    "model_name": "base",
    "input_device_indices": [],
    "glossary_file": "",
    "initial_prompt_file": "",
    "save_dir": "",
    "diarize": False,
    "hf_token": "",
    "server_url": "",
    "api_token": "",
    "max_time": None,
    "save_naming": "number",
    "no_glossary_prompt": False,
    "expose_local_api": False,
    "host": "127.0.0.1",
    "port": 8765,
    "enable_hotkeys": True,
    "dictation_hotkey": "ctrl+space",
    "save_hotkey": "ctrl+alt+n",
    "save_stop_hotkey": "ctrl+alt+space",
    "inject_typing": True,
    "copy_to_clipboard": True,
    "translate": False,
    "minimize_to_tray": True,
}


def load_gui_config():
    path = gui_config_path()
    if not os.path.isfile(path):
        return dict(DEFAULT_CONFIG)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    out = dict(DEFAULT_CONFIG)
    out.update(data)
    return out


def save_gui_config(data):
    path = gui_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _normalize_keyboard_lib_hotkey(s):
    """Match CLI normalization for the `keyboard` library (Windows-friendly)."""
    if not (s and str(s).strip()):
        return "ctrl+space"
    h = (
        str(s)
        .replace("_l", "")
        .replace("_r", "")
        .replace("cmd", "win")
        .replace("command", "win")
        .lower()
    )
    if h in ("ctrl+alt", "control+alt"):
        h = "ctrl+alt+space"
    return h


def _parse_max_time(s):
    s = (s or "").strip()
    if not s:
        return None
    return float(s)


def _collect_form_values(
    lang_var, model_var, translate_var, server_var, api_var, gloss_var, ip_var, save_var,
    save_naming_var, hf_var, max_t_var, diarize_var, no_gloss_prompt_var,
    expose_api_var, host_var, port_var, devices_listbox,
    enable_hotkeys_var, dict_hotkey_var, save_hotkey_var, save_stop_hotkey_var,
    inject_typing_var, copy_clipboard_var, minimize_to_tray_var,
):
    sel = [devices_listbox.get(i) for i in devices_listbox.curselection()]
    indices = []
    for line in sel:
        if ":" in line:
            part = line.split(":", 1)[0].strip()
            try:
                indices.append(int(part))
            except ValueError:
                pass
    return {
        "language": lang_var.get(),
        "model_name": model_var.get(),
        "translate": translate_var.get(),
        "server_url": server_var.get(),
        "api_token": api_var.get(),
        "glossary_file": gloss_var.get(),
        "initial_prompt_file": ip_var.get(),
        "save_dir": save_var.get(),
        "save_naming": save_naming_var.get(),
        "hf_token": hf_var.get(),
        "max_time": _parse_max_time(max_t_var.get()),
        "diarize": diarize_var.get(),
        "no_glossary_prompt": no_gloss_prompt_var.get(),
        "expose_local_api": expose_api_var.get(),
        "host": host_var.get(),
        "port": port_var.get(),
        "input_device_indices": indices,
        "enable_hotkeys": enable_hotkeys_var.get(),
        "dictation_hotkey": dict_hotkey_var.get(),
        "save_hotkey": save_hotkey_var.get(),
        "save_stop_hotkey": save_stop_hotkey_var.get(),
        "inject_typing": inject_typing_var.get(),
        "copy_to_clipboard": copy_clipboard_var.get(),
        "minimize_to_tray": minimize_to_tray_var.get(),
    }


def _build_args_from_form(values):
    lang = (values.get("language") or "").strip() or None
    glossary = (values.get("glossary_file") or "").strip() or None
    if glossary and not os.path.isfile(glossary):
        raise ValueError(f"Glossary file not found: {glossary}")
    ip_file = (values.get("initial_prompt_file") or "").strip() or None
    if ip_file and not os.path.isfile(ip_file):
        raise ValueError(f"Initial prompt file not found: {ip_file}")
    save_dir = (values.get("save_dir") or "").strip() or None
    server_url = (values.get("server_url") or "").strip() or None
    devs = values.get("input_device_indices") or []
    input_devices = [int(x) for x in devs] if devs else None
    mt = values.get("max_time")
    try:
        port = int(values.get("port") or 8765)
    except (TypeError, ValueError):
        port = 8765

    return SimpleNamespace(
        language=[lang] if lang else None,
        model_name=values.get("model_name") or "base",
        input_devices=input_devices,
        glossary_file=glossary,
        initial_prompt=None,
        initial_prompt_file=ip_file,
        save_dir=save_dir,
        save_naming=values.get("save_naming") or "number",
        diarize=bool(values.get("diarize")),
        diarize_model="pyannote/speaker-diarization-community-1",
        hf_token=(values.get("hf_token") or "").strip() or None,
        server_url=server_url,
        api_token=(values.get("api_token") or "").strip() or None,
        max_time=mt,
        no_glossary_prompt=bool(values.get("no_glossary_prompt")),
        host=(values.get("host") or "127.0.0.1").strip(),
        port=port,
        translate=bool(values.get("translate", False)),
    )


def gui_main():
    apply_gui_console_preference()
    app_icon.prepare_windows_taskbar_identity()
    root = tk.Tk()
    root.title("WhisperX Dictate")
    root.minsize(640, 520)
    app_icon.apply_tk_window_icon(root)

    msg_queue = queue.Queue()
    state = {
        "transcriber": None,
        "recorder": None,
        "started": False,
        "api_started": False,
        "hotkey_hooks": [],
        "tray_icon": None,
    }

    cfg = load_gui_config()
    main = ttk.Frame(root, padding=8)
    main.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    main.columnconfigure(1, weight=1)

    row = 0
    ttk.Label(main, text="Language (empty = auto):").grid(row=row, column=0, sticky="w")
    lang_var = tk.StringVar(value=cfg.get("language") or "")
    ttk.Entry(main, textvariable=lang_var, width=12).grid(row=row, column=1, sticky="w")

    row += 1
    ttk.Label(main, text="Model:").grid(row=row, column=0, sticky="w")
    model_var = tk.StringVar(value=cfg.get("model_name") or "base")
    ttk.Combobox(main, textvariable=model_var, values=MODELS, width=18, state="readonly").grid(row=row, column=1, sticky="w")

    row += 1
    translate_var = tk.BooleanVar(value=cfg.get("translate", False))
    ttk.Checkbutton(
        main,
        text="Translate speech to English (Whisper translate). When off: transcribe in the spoken language (-l is a hint only). Reload model after toggling.",
        variable=translate_var,
    ).grid(row=row, column=0, columnspan=3, sticky="w")

    row += 1
    ttk.Label(main, text="Server URL (client mode, optional):").grid(row=row, column=0, sticky="w")
    server_var = tk.StringVar(value=cfg.get("server_url") or "")
    ttk.Entry(main, textvariable=server_var, width=40).grid(row=row, column=1, sticky="ew")

    row += 1
    ttk.Label(main, text="API bearer token (optional):").grid(row=row, column=0, sticky="w")
    api_var = tk.StringVar(value=cfg.get("api_token") or "")
    ttk.Entry(main, textvariable=api_var, width=40, show="*").grid(row=row, column=1, sticky="ew")

    row += 1
    ttk.Label(main, text="Glossary TSV:").grid(row=row, column=0, sticky="w")
    gloss_var = tk.StringVar(value=cfg.get("glossary_file") or "")
    ttk.Entry(main, textvariable=gloss_var, width=40).grid(row=row, column=1, sticky="ew")

    def browse_gloss():
        p = filedialog.askopenfilename(filetypes=[("TSV", "*.tsv"), ("All", "*.*")])
        if p:
            gloss_var.set(p)

    ttk.Button(main, text="Browse…", command=browse_gloss).grid(row=row, column=2, padx=4)

    row += 1
    ttk.Label(main, text="Initial prompt file:").grid(row=row, column=0, sticky="w")
    ip_var = tk.StringVar(value=cfg.get("initial_prompt_file") or "")
    ttk.Entry(main, textvariable=ip_var, width=40).grid(row=row, column=1, sticky="ew")

    def browse_ip():
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if p:
            ip_var.set(p)

    ttk.Button(main, text="Browse…", command=browse_ip).grid(row=row, column=2, padx=4)

    row += 1
    ttk.Label(main, text="Save notes directory:").grid(row=row, column=0, sticky="w")
    save_var = tk.StringVar(value=cfg.get("save_dir") or "")
    ttk.Entry(main, textvariable=save_var, width=40).grid(row=row, column=1, sticky="ew")

    def browse_save():
        p = filedialog.askdirectory()
        if p:
            save_var.set(p)

    ttk.Button(main, text="Browse…", command=browse_save).grid(row=row, column=2, padx=4)

    row += 1
    ttk.Label(main, text="Save naming:").grid(row=row, column=0, sticky="w")
    save_naming_var = tk.StringVar(value=cfg.get("save_naming") or "number")
    ttk.Combobox(main, textvariable=save_naming_var, values=["number", "time"], width=12, state="readonly").grid(row=row, column=1, sticky="w")

    row += 1
    ttk.Label(main, text="HF token (diarization):").grid(row=row, column=0, sticky="w")
    hf_var = tk.StringVar(value=cfg.get("hf_token") or "")
    ttk.Entry(main, textvariable=hf_var, width=40, show="*").grid(row=row, column=1, sticky="ew")

    row += 1
    ttk.Label(main, text="Max recording (sec, empty = no limit):").grid(row=row, column=0, sticky="w")
    max_raw = cfg.get("max_time")
    max_t_var = tk.StringVar(value="" if max_raw in (None, "") else str(max_raw))
    ttk.Entry(main, textvariable=max_t_var, width=12).grid(row=row, column=1, sticky="w")

    row += 1
    diarize_var = tk.BooleanVar(value=cfg.get("diarize", False))
    ttk.Checkbutton(main, text="Diarization", variable=diarize_var).grid(row=row, column=1, sticky="w")

    row += 1
    no_gloss_prompt_var = tk.BooleanVar(value=cfg.get("no_glossary_prompt", False))
    ttk.Checkbutton(main, text="Glossary: replacements only (no auto initial_prompt)", variable=no_gloss_prompt_var).grid(row=row, column=1, sticky="w")

    row += 1
    expose_api_var = tk.BooleanVar(value=cfg.get("expose_local_api", False))
    ttk.Checkbutton(main, text="Expose local HTTP API (after model load; localhost)", variable=expose_api_var).grid(row=row, column=1, sticky="w")

    row += 1
    ttk.Label(main, text="API bind host:").grid(row=row, column=0, sticky="w")
    host_var = tk.StringVar(value=cfg.get("host") or "127.0.0.1")
    ttk.Entry(main, textvariable=host_var, width=20).grid(row=row, column=1, sticky="w")

    row += 1
    ttk.Label(main, text="API port:").grid(row=row, column=0, sticky="w")
    port_var = tk.StringVar(value=str(cfg.get("port") or 8765))
    ttk.Entry(main, textvariable=port_var, width=8).grid(row=row, column=1, sticky="w")

    row += 1
    enable_hotkeys_var = tk.BooleanVar(value=cfg.get("enable_hotkeys", True))
    ttk.Checkbutton(
        main,
        text="Enable global hotkeys (`keyboard` lib; Windows: run as Administrator if they fail)",
        variable=enable_hotkeys_var,
    ).grid(row=row, column=0, columnspan=3, sticky="w")

    row += 1
    ttk.Label(main, text="Dictation hotkey:").grid(row=row, column=0, sticky="w")
    dict_hotkey_var = tk.StringVar(value=cfg.get("dictation_hotkey") or "ctrl+space")
    ttk.Entry(main, textvariable=dict_hotkey_var, width=24).grid(row=row, column=1, sticky="w")

    row += 1
    ttk.Label(main, text="Save last hotkey:").grid(row=row, column=0, sticky="w")
    save_hotkey_var = tk.StringVar(value=cfg.get("save_hotkey") or "ctrl+alt+n")
    ttk.Entry(main, textvariable=save_hotkey_var, width=24).grid(row=row, column=1, sticky="w")

    row += 1
    ttk.Label(main, text="Stop + save to file hotkey:").grid(row=row, column=0, sticky="w")
    save_stop_hotkey_var = tk.StringVar(value=cfg.get("save_stop_hotkey") or "ctrl+alt+space")
    ttk.Entry(main, textvariable=save_stop_hotkey_var, width=24).grid(row=row, column=1, sticky="w")

    row += 1
    inject_typing_var = tk.BooleanVar(value=cfg.get("inject_typing", True))
    copy_clipboard_var = tk.BooleanVar(value=cfg.get("copy_to_clipboard", True))
    post_row = ttk.Frame(main)
    post_row.grid(row=row, column=0, columnspan=3, sticky="w")
    ttk.Checkbutton(
        post_row,
        text="Type into focused window after dictation (like CLI)",
        variable=inject_typing_var,
    ).pack(side=tk.LEFT, padx=(0, 12))
    ttk.Checkbutton(
        post_row,
        text="Copy transcript to clipboard after dictation",
        variable=copy_clipboard_var,
    ).pack(side=tk.LEFT)

    row += 1
    minimize_to_tray_var = tk.BooleanVar(value=cfg.get("minimize_to_tray", True))
    tray_row = ttk.Frame(main)
    tray_row.grid(row=row, column=0, columnspan=3, sticky="w")
    ttk.Checkbutton(
        tray_row,
        text="Minimize to system tray (notification area)",
        variable=minimize_to_tray_var,
    ).pack(side=tk.LEFT, padx=(0, 8))

    row += 1
    ttk.Label(main, text="Audio devices (Ctrl/Shift-click multi-select; empty = default):").grid(row=row, column=0, sticky="nw")
    dev_frame = ttk.Frame(main)
    dev_frame.grid(row=row, column=1, columnspan=2, sticky="nsew")
    devices_listbox = tk.Listbox(dev_frame, height=6, selectmode=tk.EXTENDED, exportselection=False)
    sb = ttk.Scrollbar(dev_frame, orient=tk.VERTICAL, command=devices_listbox.yview)
    devices_listbox.configure(yscrollcommand=sb.set)
    devices_listbox.grid(row=0, column=0, sticky="nsew")
    sb.grid(row=0, column=1, sticky="ns")
    dev_frame.columnconfigure(0, weight=1)
    main.rowconfigure(row, weight=1)

    def refresh_devices():
        devices_listbox.delete(0, tk.END)
        for e in list_input_devices():
            devices_listbox.insert(tk.END, f"{e['index']}: {e['name']} [{e['role']}]")
        wanted = set(cfg.get("input_device_indices") or [])
        for i in range(devices_listbox.size()):
            line = devices_listbox.get(i)
            if line.split(":", 1)[0].strip().isdigit():
                if int(line.split(":", 1)[0].strip()) in wanted:
                    devices_listbox.selection_set(i)

    refresh_devices()

    ttk.Button(main, text="Refresh devices", command=refresh_devices).grid(row=row, column=2, padx=4, sticky="ne")

    row += 1
    btn_frame = ttk.Frame(main)
    btn_frame.grid(row=row, column=0, columnspan=3, pady=8, sticky="ew")

    status_var = tk.StringVar(value="Idle — load model to start")
    ttk.Label(main, textvariable=status_var).grid(row=row + 1, column=0, columnspan=3, sticky="w")

    row += 2
    ttk.Label(main, text="Log / transcript:").grid(row=row, column=0, sticky="nw")
    text_frame = ttk.Frame(main)
    text_frame.grid(row=row, column=1, columnspan=2, sticky="nsew")
    text_frame.columnconfigure(0, weight=1)
    text_frame.rowconfigure(0, weight=1)
    main.rowconfigure(row, weight=2)
    out_text = tk.Text(text_frame, height=14, wrap=tk.WORD)
    out_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=out_text.yview)
    out_text.configure(yscrollcommand=out_scroll.set)
    out_text.grid(row=0, column=0, sticky="nsew")
    out_scroll.grid(row=0, column=1, sticky="ns")

    def append_out(s, to_stderr=False):
        out_text.insert(tk.END, s + "\n")
        out_text.see(tk.END)

    def pump_queue():
        try:
            while True:
                kind, payload = msg_queue.get_nowait()
                if kind == "msg":
                    append_out(payload)
                elif kind == "transcript":
                    append_out("→ " + payload)
                    state["last_transcript"] = payload
                    status_var.set("Ready")
                elif kind == "status":
                    status_var.set(payload)
                elif kind == "load_ok":
                    (
                        transcriber,
                        recorder,
                        expose,
                        host,
                        port,
                        lang0,
                        api_token,
                        load_gen,
                    ) = payload
                    cur_gen = int(state.get("_load_gen", 0))
                    stale = load_gen != cur_gen
                    if stale:
                        _release_transcriber_resources(transcriber)
                        continue
                    state["transcriber"] = transcriber
                    state["recorder"] = recorder
                    state["started"] = False
                    rec_btn.configure(text="Start recording")
                    if expose and not state["api_started"]:
                        try:
                            run_server_in_thread(
                                transcriber,
                                host,
                                port,
                                language=lang0,
                                api_token=api_token,
                            )
                        except Exception as e:
                            append_out(f"(API thread failed: {e})")
                        else:
                            state["api_started"] = True
                            append_out(f"Local API: http://{host}:{port}/")
                    status_var.set("Ready")
                    load_btn.configure(state=tk.NORMAL)
                    rec_btn.configure(state=tk.NORMAL)
                    register_gui_hotkeys()
                elif kind == "load_err":
                    append_out(payload)
                    status_var.set("Load failed")
                    load_btn.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        root.after(150, pump_queue)

    def do_load():
        unregister_gui_hotkeys()
        rec0 = state.get("recorder")
        if rec0 is not None and state.get("started"):
            status_var.set("Stopping recording before reload…")
            root.update_idletasks()
            rec0.stop()
            rec0.join()
            state["started"] = False
            rec_btn.configure(text="Start recording")
        old_tr = state.get("transcriber")
        state["transcriber"] = None
        state["recorder"] = None
        _release_transcriber_resources(old_tr)
        state["_load_gen"] = int(state.get("_load_gen", 0)) + 1
        load_gen = state["_load_gen"]
        try:
            vals = _collect_form_values(
                lang_var, model_var, translate_var, server_var, api_var, gloss_var, ip_var, save_var,
                save_naming_var, hf_var, max_t_var, diarize_var, no_gloss_prompt_var,
                expose_api_var, host_var, port_var, devices_listbox,
                enable_hotkeys_var, dict_hotkey_var, save_hotkey_var, save_stop_hotkey_var,
                inject_typing_var, copy_clipboard_var, minimize_to_tray_var,
            )
            args_obj = _build_args_from_form(vals)
        except (ValueError, TypeError) as e:
            messagebox.showerror("Invalid settings", str(e))
            return
        save_gui_config(vals)
        cfg.update(vals)
        load_btn.configure(state=tk.DISABLED)
        state["api_started"] = False
        status_var.set("Loading model / connecting…")
        expose = expose_api_var.get() and not (args_obj.server_url)
        try:
            host = host_var.get().strip() or "127.0.0.1"
            port = int(port_var.get().strip() or "8765")
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be an integer.")
            load_btn.configure(state=tk.NORMAL)
            return

        inject_t = inject_typing_var.get()
        copy_clip = copy_clipboard_var.get()

        def worker():
            gen = load_gen
            try:
                glossary_pairs, initial_prompt, user_prompt, auto_from_glossary = prepare_glossary_and_prompt(
                    args_obj, emit_print=False,
                )

                def on_message(line):
                    msg_queue.put(("msg", line))

                def on_transcript(text):
                    msg_queue.put(("transcript", text))

                transcriber = build_transcriber(
                    args_obj,
                    glossary_pairs,
                    initial_prompt,
                    user_prompt,
                    auto_from_glossary,
                    emit_print=False,
                    on_message=on_message,
                    on_transcript=on_transcript,
                    inject_typing=inject_t,
                    copy_to_clipboard=copy_clip,
                )
                recorder = build_recorder(transcriber, args_obj, on_message=on_message)
                lang0 = args_obj.language[0] if args_obj.language else None
                api_token = args_obj.api_token
                msg_queue.put(
                    ("load_ok", (transcriber, recorder, expose, host, port, lang0, api_token, gen)),
                )
            except Exception as e:
                msg_queue.put(("load_err", f"Load failed: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def unregister_gui_hotkeys():
        try:
            import keyboard as kb

            kb.unhook_all()
        except ImportError:
            pass
        except Exception:
            pass
        state.pop("hotkey_hooks", None)

    def register_gui_hotkeys():
        unregister_gui_hotkeys()
        if not enable_hotkeys_var.get():
            return
        try:
            import keyboard as kb
        except ImportError:
            append_out("(install keyboard for global hotkeys: pip install keyboard)")
            return
        dh = _normalize_keyboard_lib_hotkey(dict_hotkey_var.get())
        sh = _normalize_keyboard_lib_hotkey(save_hotkey_var.get())
        ssh = _normalize_keyboard_lib_hotkey(save_stop_hotkey_var.get())
        hooks = []
        try:
            with hotkey_registration_layout_fix():
                kb.add_hotkey(dh, lambda: root.after(0, toggle_record), suppress=False)
                hooks.append(dh)
                kb.add_hotkey(sh, lambda: root.after(0, save_note), suppress=False)
                hooks.append(sh)
                kb.add_hotkey(ssh, lambda: root.after(0, stop_and_save_gui), suppress=False)
                hooks.append(ssh)
        except Exception as e:
            append_out(f"(hotkey registration failed: {e})")
            return
        state["hotkey_hooks"] = hooks
        append_out(f"(global hotkeys: dictate {dh} | save {sh} | stop+save {ssh})")

    def stop_and_save_gui():
        rec = state.get("recorder")
        if not rec or not state["started"]:
            return
        status_var.set("Stopping (save to file)…")
        rec.transcriber._save_on_next = True
        rec.stop()
        state["started"] = False
        rec_btn.configure(text="Start recording")
        status_var.set("Ready")

    def toggle_record():
        rec = state.get("recorder")
        if not rec:
            messagebox.showinfo("Not ready", "Load model first.")
            return
        if state["started"]:
            status_var.set("Stopping…")
            rec.stop()
            state["started"] = False
            rec_btn.configure(text="Start recording")
            status_var.set("Ready")
        else:
            lang = None
            la = lang_var.get().strip()
            if la:
                lang = la
            try:
                mt = _parse_max_time(max_t_var.get())
            except ValueError:
                messagebox.showerror("Invalid max time", "Enter a number or leave empty.")
                return
            tr = state.get("transcriber")
            if tr:
                tr.inject_typing = inject_typing_var.get()
                tr.copy_to_clipboard = copy_clipboard_var.get()
            status_var.set("Recording…")
            state["started"] = True
            rec_btn.configure(text="Stop recording")
            rec.start(lang, mt)

    def copy_clipboard():
        try:
            import pyperclip
            t = ""
            if state.get("transcriber") and getattr(state["transcriber"], "_last_text", None):
                t = state["transcriber"]._last_text
            if not t:
                t = out_text.get("1.0", tk.END).strip()
            if not t:
                messagebox.showinfo("Clipboard", "Nothing to copy.")
                return
            pyperclip.copy(t)
            messagebox.showinfo("Clipboard", "Copied.")
        except Exception as e:
            messagebox.showerror("Clipboard", str(e))

    def save_note():
        tr = state.get("transcriber")
        if not tr:
            return
        try:
            tr.save_last_to_note()
        except Exception as e:
            messagebox.showerror("Save", str(e))

    hiding_to_tray = [False]

    def show_main_window():
        root.deiconify()
        root.state("normal")
        root.lift()
        try:
            root.focus_force()
        except tk.TclError:
            pass

    def stop_tray_icon():
        icon = state.get("tray_icon")
        if not icon:
            return
        try:
            icon.stop()
        except Exception:
            pass
        state["tray_icon"] = None

    def on_close():
        unregister_gui_hotkeys()
        stop_tray_icon()
        try:
            root.destroy()
        except tk.TclError:
            pass

    def ensure_tray():
        if not tray_support.tray_available():
            return
        if state.get("tray_icon"):
            return

        def on_open():
            root.after(0, show_main_window)

        def on_quit():
            root.after(0, on_close)

        state["tray_icon"] = tray_support.create_tray_icon(
            "WhisperX Dictate",
            on_open,
            on_quit,
        )

    def handle_unmap(event):
        if event.widget != root or hiding_to_tray[0]:
            return
        if not minimize_to_tray_var.get():
            return
        if not tray_support.tray_available():
            return
        root.after(200, check_iconic_and_hide)

    def check_iconic_and_hide():
        try:
            if not root.winfo_exists():
                return
            if root.state() != "iconic":
                return
            if not minimize_to_tray_var.get():
                return
        except tk.TclError:
            return
        ensure_tray()
        hiding_to_tray[0] = True
        root.withdraw()
        root.after(0, _end_hide_to_tray)

    def _end_hide_to_tray():
        hiding_to_tray[0] = False

    def hide_to_tray_manual():
        if not tray_support.tray_available():
            messagebox.showinfo(
                "System tray",
                "Optional: pip install pystray pillow",
            )
            return
        ensure_tray()
        hiding_to_tray[0] = True
        root.withdraw()
        root.after(0, _end_hide_to_tray)

    ttk.Button(tray_row, text="Hide to tray", command=hide_to_tray_manual).pack(side=tk.LEFT)

    root.bind("<Unmap>", handle_unmap)

    load_btn = ttk.Button(btn_frame, text="Load model / connect", command=do_load)
    load_btn.pack(side=tk.LEFT, padx=4)
    rec_btn = ttk.Button(btn_frame, text="Start recording", command=toggle_record, state=tk.DISABLED)
    rec_btn.pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Copy last to clipboard", command=copy_clipboard).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Save last to note", command=save_note).pack(side=tk.LEFT, padx=4)

    root.protocol("WM_DELETE_WINDOW", on_close)

    root.after(100, pump_queue)

    root.mainloop()


if __name__ == "__main__":
    gui_main()
