import time


class CLIApp:
    def __init__(self, recorder, languages=None, max_time=None):
        self.recorder = recorder
        self.languages = languages
        self.max_time = max_time
        self.started = False

    def toggle(self):
        if self.started:
            print("Stopping...")
            self.recorder.stop()
            self.started = False
        else:
            print("Starting...")
            self.recorder.start(self.languages[0] if self.languages else None, self.max_time)
            self.started = True

    def run(self):
        print("CLI dictation running. Use your key combination to toggle recording.")
        while True:
            time.sleep(1)

    def stop_and_save(self):
        if not self.started:
            return
        print("Stopping (save to file)...")
        self.recorder.transcriber._save_on_next = True
        self.recorder.stop()
        self.started = False

    def save_last_note(self):
        self.recorder.transcriber.save_last_to_note()


class CLIAppEnter:
    """Use Enter in the terminal to start/stop recording (no global hotkey)."""

    def __init__(self, recorder, languages=None, max_time=None):
        self.recorder = recorder
        self.languages = languages
        self.max_time = max_time
        self.started = False

    def toggle(self):
        if self.started:
            print("Stopping...")
            self.recorder.stop()
            self.started = False
        else:
            print("Starting...")
            self.recorder.start(self.languages[0] if self.languages else None, self.max_time)
            self.started = True

    def run(self):
        print("Enter-to-toggle mode: focus this window and press Enter to start, Enter again to stop.")
        while True:
            try:
                input()
                self.toggle()
            except (EOFError, KeyboardInterrupt):
                break

    def stop_and_save(self):
        if not self.started:
            return
        print("Stopping (save to file)...")
        self.recorder.transcriber._save_on_next = True
        self.recorder.stop()
        self.started = False

    def save_last_note(self):
        self.recorder.transcriber.save_last_to_note()
