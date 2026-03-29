"""Build transcriber and recorder from CLI/GUI-style argument namespace."""

import os

from whisperx_dictate.glossary import glossary_initial_prompt, load_glossary_tsv
from whisperx_dictate.recorder import Recorder
from whisperx_dictate.transcribers import (
    ClientTranscriber,
    PRESET_CUSTOM_CHAR_DELAY_MS,
    PRESET_CUSTOM_SPACE_EXTRA_MS,
    SpeechTranscriber,
)


def resolve_initial_prompt(args):
    """Return stripped initial_prompt string for whisperx load_model asr_options, or None."""
    if getattr(args, "initial_prompt_file", None):
        with open(args.initial_prompt_file, encoding="utf-8") as f:
            s = f.read().strip()
        return s if s else None
    if getattr(args, "initial_prompt", None):
        s = args.initial_prompt.strip()
        return s if s else None
    return None


def prepare_glossary_and_prompt(args, emit_print=True):
    """Load glossary pairs and compute initial_prompt for ASR. Returns (glossary_pairs, initial_prompt, user_prompt, auto_from_glossary)."""
    glossary_pairs = []
    if getattr(args, "glossary_file", None):
        glossary_pairs = load_glossary_tsv(args.glossary_file)
        if emit_print:
            print("(glossary: {} replacement rows)".format(len(glossary_pairs)))

    user_prompt = resolve_initial_prompt(args)
    use_glossary_prompt = glossary_pairs and not getattr(args, "no_glossary_prompt", False)
    auto_from_glossary = glossary_initial_prompt(glossary_pairs) if use_glossary_prompt else None
    initial_prompt = user_prompt or auto_from_glossary
    return glossary_pairs, initial_prompt, user_prompt, auto_from_glossary


def build_transcriber(args, glossary_pairs, initial_prompt, user_prompt, auto_from_glossary, emit_print=True, **transcriber_kw):
    """Create SpeechTranscriber or ClientTranscriber. transcriber_kw passed to constructors (on_message, inject_typing, etc.)."""
    lang = args.language[0] if args.language else None
    server_url = getattr(args, "server_url", None)
    kw = dict(transcriber_kw)
    use_custom = bool(getattr(args, "inject_type_use_custom_delays", False))
    if use_custom:
        kw.setdefault("inject_type_use_custom_delays", True)
        kw.setdefault(
            "inject_type_char_delay_ms",
            float(getattr(args, "inject_type_char_delay_ms", PRESET_CUSTOM_CHAR_DELAY_MS)),
        )
        kw.setdefault(
            "inject_type_space_extra_ms",
            float(getattr(args, "inject_type_space_extra_ms", PRESET_CUSTOM_SPACE_EXTRA_MS)),
        )
    else:
        kw.setdefault("inject_type_use_custom_delays", False)
        inj_ms = getattr(args, "inject_type_delay_ms", None)
        if inj_ms is not None:
            kw.setdefault("inject_type_delay_ms", float(inj_ms))

    if server_url:
        if emit_print:
            print("Client mode: using server", server_url, "(no local model)")
            if auto_from_glossary and not user_prompt:
                print(
                    "(note: ASR initial_prompt from glossary applies only on the server; "
                    "pass the same --glossary-file there, or use --initial-prompt on the server)"
                )
        return ClientTranscriber(
            server_url,
            language=lang,
            diarize=getattr(args, "diarize", False),
            api_token=getattr(args, "api_token", None),
            glossary_pairs=glossary_pairs,
            **kw,
        )

    import torch
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_name = args.model_name
    if model_name == "large":
        model_name = "large-v2"
    task = "translate" if getattr(args, "translate", False) else "transcribe"
    if task == "translate" and str(model_name).endswith(".en") and emit_print:
        print("(warning: translate works best with multilingual models, not *.en)")

    if emit_print:
        print(f"Loading model ({model_name}) on {device} (task={task})...")
    asr_options = {"initial_prompt": initial_prompt} if initial_prompt else None
    if initial_prompt and emit_print:
        src = "glossary (compact)" if not user_prompt and auto_from_glossary else "explicit"
        print("(using ASR initial_prompt [{}], {} chars)".format(src, len(initial_prompt)))
    model = whisperx.load_model(model_name, device, language=lang, asr_options=asr_options, task=task)
    if emit_print:
        print(f"{model_name} model loaded")
    return SpeechTranscriber(
        model,
        save_dir=getattr(args, "save_dir", None),
        save_naming=getattr(args, "save_naming", "number"),
        diarize=getattr(args, "diarize", False),
        hf_token=getattr(args, "hf_token", None),
        diarize_model=getattr(args, "diarize_model", "pyannote/speaker-diarization-community-1"),
        device=device,
        glossary_pairs=glossary_pairs,
        **kw,
    )


def build_recorder(transcriber, args, on_message=None):
    return Recorder(transcriber, input_devices=getattr(args, "input_devices", None), on_message=on_message)
