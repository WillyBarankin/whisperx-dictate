from pynput import keyboard


def is_modifier_key(key, modifier_name):
    """Return True if key is the given modifier or key (ctrl, alt, space, etc.)."""
    name = modifier_name.lower()
    if hasattr(key, "vk") and key.vk is not None:
        vk = key.vk
        if name in ("ctrl", "control"):
            return vk in (0x11, 0xA2, 0xA3)
        if name == "alt":
            return vk in (0x12, 0xA4, 0xA5)
        if name == "space":
            return vk == 0x20
    try:
        attr = getattr(keyboard.Key, name, None)
        if attr is not None and key == attr:
            return True
    except (AttributeError, TypeError):
        pass
    for variant in (name, name.replace("_l", "").replace("_r", "")):
        attr = getattr(keyboard.Key, variant, None)
        if attr is not None and key == attr:
            return True
    return False


class GlobalKeyListener:
    def __init__(self, app, key_combination):
        self.app = app
        self.key1_name, self.key2_name = key_combination.split("+")
        self.key1_pressed = False
        self.key2_pressed = False

    def on_key_press(self, key):
        if is_modifier_key(key, self.key1_name):
            self.key1_pressed = True
        elif is_modifier_key(key, self.key2_name):
            self.key2_pressed = True

        if self.key1_pressed and self.key2_pressed:
            self.app.toggle()

    def on_key_release(self, key):
        if is_modifier_key(key, self.key1_name):
            self.key1_pressed = False
        elif is_modifier_key(key, self.key2_name):
            self.key2_pressed = False


class DoubleCommandKeyListener:
    def __init__(self, app):
        self.app = app
        self.key = keyboard.Key.cmd_r
        self.pressed = 0
        self.last_press_time = 0

    def on_key_press(self, key):
        import time
        is_listening = self.app.started
        if key == self.key:
            current_time = time.time()
            if not is_listening and current_time - self.last_press_time < 0.5:
                self.app.toggle()
            elif is_listening:
                self.app.toggle()
            self.last_press_time = current_time

    def on_key_release(self, key):
        pass
