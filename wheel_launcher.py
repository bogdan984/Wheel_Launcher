# -*- coding: utf-8 -*-
"""Wheel Launcher: поворот руля, педали, кнопки и D-pad руля -> нажатия клавиш клавиатуры (Windows, SendInput).

Руль VID 0x0079 PID 0x1864 («Wired Wheel», D-Input). Игра видит обычную клавиатуру.
Несколько профилей с переключением кнопкой руля / клавишей, название профиля поверх игры,
подписи привязок, подсветка нажатой на руле привязки.
Запуск: python wheel_launcher.py   (нужен pygame==2.6.1)
"""
import copy
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
APP_NAME = "Wheel Launcher"
APP_VERSION = "2.1.1"
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
AXIS_NAMES = ["X", "Y", "Z", "R", "U", "V"]
HYST = 0.10  # гистерезис оси: отпускается на 10 % ниже порога нажатия

# ----------------------------------------------------------------------
# Клавиши: имя -> (scan-код set 1, extended)
# ----------------------------------------------------------------------
KEYS = {}
for _i, _c in enumerate("qwertyuiop"):
    KEYS[_c] = (0x10 + _i, False)
for _i, _c in enumerate("asdfghjkl"):
    KEYS[_c] = (0x1E + _i, False)
for _i, _c in enumerate("zxcvbnm"):
    KEYS[_c] = (0x2C + _i, False)
for _i, _c in enumerate("1234567890"):
    KEYS[_c] = (0x02 + _i, False)
for _i in range(10):
    KEYS["f%d" % (_i + 1)] = (0x3B + _i, False)
KEYS.update({
    "f11": (0x57, False), "f12": (0x58, False),
    "space": (0x39, False), "return": (0x1C, False), "escape": (0x01, False),
    "tab": (0x0F, False), "backspace": (0x0E, False),
    "shift_l": (0x2A, False), "control_l": (0x1D, False), "alt_l": (0x38, False),
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "prior": (0x49, True), "next": (0x51, True), "home": (0x47, True), "end": (0x4F, True),
    "insert": (0x52, True), "delete": (0x53, True),
})

# Цифровой блок (scan-коды NumPad: игра видит именно «Num 5», а не «5» верхнего ряда), знаки, правые модификаторы
for _i, _sc in enumerate((0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49)):
    KEYS["num%d" % _i] = (_sc, False)
KEYS.update({
    "num_dec": (0x53, False), "num_add": (0x4E, False), "num_sub": (0x4A, False), "num_mul": (0x37, False),
    "num_div": (0x35, True), "num_enter": (0x1C, True),
    "minus": (0x0C, False), "equals": (0x0D, False), "lbracket": (0x1A, False), "rbracket": (0x1B, False),
    "semicolon": (0x27, False), "apostrophe": (0x28, False), "grave": (0x29, False), "backslash": (0x2B, False),
    "comma": (0x33, False), "period": (0x34, False), "slash": (0x35, False),
    "capslock": (0x3A, False), "shift_r": (0x36, False), "control_r": (0x1D, True), "alt_r": (0x38, True),
})

# Виртуальные коды тех же клавиш: для опроса клавиши переключения профилей, когда в фокусе игра
VK = {k: ord(k.upper()) for k in KEYS if len(k) == 1}
VK.update({"f%d" % (i + 1): 0x70 + i for i in range(12)})
VK.update({"space": 0x20, "return": 0x0D, "escape": 0x1B, "tab": 0x09, "backspace": 0x08,
           "shift_l": 0xA0, "control_l": 0xA2, "alt_l": 0xA4, "up": 0x26, "down": 0x28, "left": 0x25,
           "right": 0x27, "prior": 0x21, "next": 0x22, "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E})
VK.update({"num%d" % i: 0x60 + i for i in range(10)})
VK.update({"num_mul": 0x6A, "num_add": 0x6B, "num_sub": 0x6D, "num_dec": 0x6E, "num_div": 0x6F, "num_enter": 0x0D,
           "minus": 0xBD, "equals": 0xBB, "lbracket": 0xDB, "rbracket": 0xDD, "semicolon": 0xBA,
           "apostrophe": 0xDE, "grave": 0xC0, "backslash": 0xDC, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
           "capslock": 0x14, "shift_r": 0xA1, "control_r": 0xA3, "alt_r": 0xA5})

# Порядок и названия в выпадающем списке: буквы, цифры, знаки, цифровой блок, F-клавиши, служебные, стрелки
KEY_ORDER = (list("abcdefghijklmnopqrstuvwxyz") + list("1234567890") +
             ["grave", "minus", "equals", "lbracket", "rbracket", "semicolon", "apostrophe", "backslash",
              "comma", "period", "slash"] +
             ["num%d" % i for i in range(10)] + ["num_div", "num_mul", "num_sub", "num_add", "num_enter", "num_dec"] +
             ["f%d" % i for i in range(1, 13)] +
             ["escape", "backspace", "tab", "return", "capslock", "space", "shift_l", "shift_r", "control_l",
              "control_r", "alt_l", "alt_r", "insert", "home", "prior", "delete", "end", "next",
              "up", "down", "left", "right"])
assert sorted(KEY_ORDER) == sorted(KEYS), "KEY_ORDER должен содержать все клавиши"
_KEY_TEXT = {"grave": "` (Ё)", "minus": "-", "equals": "=", "lbracket": "[ (Х)", "rbracket": "] (Ъ)",
             "semicolon": "; (Ж)", "apostrophe": "' (Э)", "backslash": "\\", "comma": ", (Б)", "period": ". (Ю)",
             "slash": "/", "num_div": "Num /", "num_mul": "Num *", "num_sub": "Num -", "num_add": "Num +",
             "num_enter": "Num Enter", "num_dec": "Num .", "escape": "Esc", "backspace": "Backspace", "tab": "Tab",
             "return": "Enter", "capslock": "CapsLock", "space": "Пробел", "shift_l": "Shift (лев.)",
             "shift_r": "Shift (прав.)", "control_l": "Ctrl (лев.)", "control_r": "Ctrl (прав.)",
             "alt_l": "Alt (лев.)", "alt_r": "Alt (прав.)", "insert": "Insert", "home": "Home", "prior": "PgUp",
             "delete": "Delete", "end": "End", "next": "PgDn", "up": "Стрелка вверх", "down": "Стрелка вниз",
             "left": "Стрелка влево", "right": "Стрелка вправо"}


def key_label(k):
    """Название клавиши для людей: num5 -> «Num 5»."""
    if k in _KEY_TEXT:
        return _KEY_TEXT[k]
    if k.startswith("num") and k[3:].isdigit():
        return "Num " + k[3:]
    return k.upper()


PAD_ORDER = ["pad_a", "pad_b", "pad_x", "pad_y", "pad_lb", "pad_rb", "pad_ls", "pad_rs", "pad_back", "pad_start",
             "pad_dpad_up", "pad_dpad_down", "pad_dpad_left", "pad_dpad_right"]
PAD_BUTTONS = {"pad_a": "Геймпад A", "pad_b": "Геймпад B", "pad_x": "Геймпад X", "pad_y": "Геймпад Y",
               "pad_lb": "Геймпад LB (левый бампер)", "pad_rb": "Геймпад RB (правый бампер)",
               "pad_ls": "Геймпад LS (нажатие левого стика)", "pad_rs": "Геймпад RS (нажатие правого стика)",
               "pad_back": "Геймпад Back", "pad_start": "Геймпад Start", "pad_dpad_up": "Геймпад D-pad вверх",
               "pad_dpad_down": "Геймпад D-pad вниз", "pad_dpad_left": "Геймпад D-pad влево",
               "pad_dpad_right": "Геймпад D-pad вправо"}
PICK_ORDER = KEY_ORDER + PAD_ORDER


def key_label(k, _old=key_label):
    return PAD_BUTTONS[k] if k in PAD_BUTTONS else _old(k)


KEY_BY_LABEL = {key_label(k): k for k in PICK_ORDER}
_KP_KEYSYM = {"KP_Enter": "num_enter", "KP_Multiply": "num_mul", "KP_Add": "num_add", "KP_Subtract": "num_sub",
              "KP_Decimal": "num_dec", "KP_Divide": "num_div"}
_VK_TO_KEY = {v: k for k, v in VK.items() if k.startswith("num") and k != "num_enter"}
_VK_TO_KEY.update({VK[k]: k for k in ("minus", "equals", "lbracket", "rbracket", "semicolon", "apostrophe",
                                      "grave", "backslash", "comma", "period", "slash")})


def key_from_event(keycode, keysym):
    """Имя клавиши из события Tk. На Windows keycode = VK: буквы/цифры не зависят от раскладки (русская тоже),
    цифровой блок отличается от верхнего ряда."""
    if keysym in _KP_KEYSYM:
        return _KP_KEYSYM[keysym]
    if keycode in _VK_TO_KEY:
        return _VK_TO_KEY[keycode]
    if 0x41 <= keycode <= 0x5A:
        return chr(keycode).lower()
    if 0x30 <= keycode <= 0x39:
        return chr(keycode)
    return keysym.lower()


# ----------------------------------------------------------------------
# Отправка клавиш
# ----------------------------------------------------------------------
class NullInput(object):
    def __init__(self):
        self.log = []

    def send(self, key, down):
        self.log.append((key, down))


class WinInput(object):
    """SendInput со scan-кодами: игры видят их как настоящую клавиатуру."""

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        WORD, DWORD, LONG, UINT = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32
        ULONG_PTR = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                        ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]

        class MOUSEINPUT(ctypes.Structure):  # нужен только ради правильного размера union
            _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                        ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", DWORD), ("u", _U)]

        self.INPUT, self.KEYBDINPUT = INPUT, KEYBDINPUT
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = (UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self.user32.SendInput.restype = UINT

    def send(self, key, down):
        scan, ext = KEYS[key]
        flags = 0x0008 | (0x0001 if ext else 0) | (0 if down else 0x0002)  # SCANCODE | EXTENDED | KEYUP
        inp = self.INPUT()
        inp.type = 1  # INPUT_KEYBOARD
        inp.ki = self.KEYBDINPUT(0, scan, flags, 0, 0)
        self.user32.SendInput(1, self.ctypes.byref(inp), self.ctypes.sizeof(inp))


VIGEM_URL = "https://github.com/nefarius/ViGEmBus/releases"


def vigem_installed():
    """Драйвер ViGEmBus в системе: True / False; None — не Windows. Проверка по службе, геймпад не создаётся."""
    if not IS_WIN:
        return None
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\ViGEmBus"))
        return True
    except OSError:
        return False


def vigem_status(installed, enabled):
    """(текст, всё ли в порядке) для строки состояния драйвера."""
    if installed is None:
        return "ViGEmBus: проверка доступна только в Windows", True
    if installed:
        return "ViGEmBus: драйвер установлен — виртуальный геймпад доступен", True
    return ("ViGEmBus: драйвер НЕ установлен" + (" — геймпад в этом профиле включён, но работать не будет" if enabled else "")
            + ". Скачайте ViGEmBus_…_x64_x86_arm64.exe, установите и перезагрузите ПК", False)


class PadOutput(object):
    """Виртуальный геймпад Xbox 360 (драйвер ViGEmBus + библиотека vgamepad). Создаётся при первом обращении."""
    XUSB = {"pad_a": "A", "pad_b": "B", "pad_x": "X", "pad_y": "Y", "pad_lb": "LEFT_SHOULDER",
            "pad_rb": "RIGHT_SHOULDER", "pad_ls": "LEFT_THUMB", "pad_rs": "RIGHT_THUMB", "pad_back": "BACK",
            "pad_start": "START", "pad_dpad_up": "DPAD_UP", "pad_dpad_down": "DPAD_DOWN",
            "pad_dpad_left": "DPAD_LEFT", "pad_dpad_right": "DPAD_RIGHT"}

    def __init__(self):
        self.pad, self.vg, self.err, self.last = None, None, "", None

    def ensure(self):
        if self.pad is not None:
            return True
        try:
            import vgamepad as vg
            pad = vg.VX360Gamepad()
            pad.reset()
            pad.update()
            self.vg, self.pad = vg, pad
            return True
        except Exception as e:  # noqa
            self.err = "%s: %s" % (type(e).__name__, e)
            return False

    def button(self, name, down):
        if not self.ensure():
            return
        b = getattr(self.vg.XUSB_BUTTON, "XUSB_GAMEPAD_" + self.XUSB[name])
        (self.pad.press_button if down else self.pad.release_button)(button=b)
        self.pad.update()

    def axes(self, steer, rt, lt):
        """Левый стик по X (руль), правый триггер (газ), левый триггер (тормоз). Шлёт только изменения."""
        cur = (round(steer, 3), round(rt, 3), round(lt, 3))
        if cur == self.last or not self.ensure():
            return
        self.last = cur
        self.pad.left_joystick_float(x_value_float=cur[0], y_value_float=0.0)
        self.pad.right_trigger_float(value_float=cur[1])
        self.pad.left_trigger_float(value_float=cur[2])
        self.pad.update()

    def reset(self):
        self.last = None
        if self.pad is not None:
            self.pad.reset()
            self.pad.update()


class Output(object):
    """Для Engine: «pad_*» -> виртуальный геймпад, остальное -> клавиатура."""

    def __init__(self, kb=None, pad=None):
        self.kb = kb if kb is not None else (WinInput() if IS_WIN else NullInput())
        self.pad = pad if pad is not None else PadOutput()

    def send(self, key, down):
        if key in PAD_BUTTONS:
            self.pad.button(key, down)
        else:
            self.kb.send(key, down)


# ----------------------------------------------------------------------
# Привязки. Вход: "axis0-" "axis1+" (ось, сторона), "btn5", "hat0U/D/L/R"
# ----------------------------------------------------------------------
HAT_DIRS = {"U": (0, 1), "D": (0, -1), "L": (-1, 0), "R": (1, 0)}


def input_label(name):
    if name.startswith("axis"):
        n = int(name[4:-1])
        return "Ось %s %s" % (AXIS_NAMES[n] if n < len(AXIS_NAMES) else n, "−" if name[-1] == "-" else "+")
    if name.startswith("btn"):
        return "Кнопка %d" % (int(name[3:]) + 1)
    if name.startswith("hat"):
        return "D-pad %s" % {"U": "вверх", "D": "вниз", "L": "влево", "R": "вправо"}[name[-1]]
    return name


class Engine(object):
    """Каждый тик: сравнивает состояние руля с привязками и нажимает/отпускает клавиши."""

    def __init__(self, backend=None):
        self.backend = backend if backend is not None else (WinInput() if IS_WIN else NullInput())
        self.on = set()    # индексы сработавших привязок
        self.count = {}    # клавиша -> сколько привязок её держат

    @staticmethod
    def _active(b, was_on, axes, buttons, hats):
        name = b["input"]
        if name.startswith("axis"):
            n = int(name[4:-1])
            if n >= len(axes):
                return False
            v = axes[n] * (1 if name[-1] == "+" else -1)
            thr = max(b.get("threshold", 30) / 100.0, 0.05)
            return v >= (thr - HYST if was_on else thr)
        if name.startswith("btn"):
            n = int(name[3:])
            return n < len(buttons) and bool(buttons[n])
        if name.startswith("hat"):
            n = int(name[3]) if name[3].isdigit() else 0
            return n < len(hats) and tuple(hats[n]) == HAT_DIRS[name[-1]]
        return False

    def update(self, bindings, axes, buttons, hats):
        for i, b in enumerate(bindings):
            if b["key"] not in KEYS and b["key"] not in PAD_BUTTONS:
                continue
            act = self._active(b, i in self.on, axes, buttons, hats)
            if act and i not in self.on:
                self.on.add(i)
                self.count[b["key"]] = self.count.get(b["key"], 0) + 1
                if self.count[b["key"]] == 1:
                    self.backend.send(b["key"], True)
            elif not act and i in self.on:
                self.on.discard(i)
                self.count[b["key"]] -= 1
                if self.count[b["key"]] == 0:
                    self.backend.send(b["key"], False)

    def release_all(self):
        for k, c in list(self.count.items()):
            if c > 0:
                self.backend.send(k, False)
        self.count.clear()
        self.on.clear()


def detect_input(base_axes, axes, buttons, hats):
    """Что пользователь сейчас задействовал: ось (сдвиг от базы > 50 %), кнопка или D-pad. Иначе None."""
    for n, v in enumerate(axes):
        d = v - base_axes[n]
        if abs(d) > 0.5:
            return "axis%d%s" % (n, "+" if d > 0 else "-")
    for n, p in enumerate(buttons):
        if p:
            return "btn%d" % n
    for n, h in enumerate(hats):
        for k, d in HAT_DIRS.items():
            if tuple(h) == d:
                return "hat%d%s" % (n, k)
    return None




PAD_DEFAULT = {"enabled": False, "axis": 0, "invert": False, "deadzone": 3, "range": 100,
               "throttle": None, "brake": None}


def sanitize_pad(o):
    o = o if isinstance(o, dict) else {}
    d = PAD_DEFAULT

    def num(k, lo, hi):
        v = o.get(k)
        return max(lo, min(hi, int(v))) if isinstance(v, (int, float)) and not isinstance(v, bool) else d[k]
    return {"enabled": bool(o.get("enabled", False)), "axis": num("axis", 0, 15), "invert": bool(o.get("invert", False)),
            "deadzone": num("deadzone", 0, 30), "range": num("range", 10, 100),
            "throttle": o["throttle"] if isinstance(o.get("throttle"), str) else None,
            "brake": o["brake"] if isinstance(o.get("brake"), str) else None}


def steer_value(v, deadzone, rng, invert):
    """Поворот руля (-1..1) -> стик (-1..1): мёртвая зона в центре, rng % хода руля = полный поворот колёс."""
    a, dz, full = abs(v), deadzone / 100.0, max(rng / 100.0, deadzone / 100.0 + 0.05)
    out = 0.0 if a <= dz else min(1.0, (a - dz) / (full - dz))
    return out * (1 if v >= 0 else -1) * (-1 if invert else 1)


def pedal_value(name, axes, buttons, hats, deadzone=3):
    """Педаль/кнопка -> 0..1: ось — плавно (нужная сторона оси), кнопка/D-pad — 0 или 1."""
    if not name:
        return 0.0
    if name.startswith("axis"):
        n = int(name[4:-1])
        if n >= len(axes):
            return 0.0
        v = axes[n] * (1 if name[-1] == "+" else -1)
        dz = deadzone / 100.0
        return 0.0 if v <= dz else min(1.0, (v - dz) / (1.0 - dz))
    return 1.0 if Engine._active({"input": name}, False, axes, buttons, hats) else 0.0


def pad_values(pd, axes, buttons, hats):
    """(руль, газ, тормоз) для виртуального геймпада."""
    steer = steer_value(axes[pd["axis"]], pd["deadzone"], pd["range"], pd["invert"]) if pd["axis"] < len(axes) else 0.0
    return (steer, pedal_value(pd["throttle"], axes, buttons, hats, pd["deadzone"]),
            pedal_value(pd["brake"], axes, buttons, hats, pd["deadzone"]))


def pad_busy(pd):
    """Входы руля, которыми управляет геймпад: клавиши на них не нажимаются."""
    if not pd["enabled"]:
        return set()
    return {"axis%d+" % pd["axis"], "axis%d-" % pd["axis"]} | {x for x in (pd["throttle"], pd["brake"]) if x}


def active_rows(bindings, axes, buttons, hats):
    """Индексы привязок, чей вход руля сейчас нажат (для подсветки в окне)."""
    return {i for i, b in enumerate(bindings) if Engine._active(b, False, axes, buttons, hats)}


def pressed_inputs(buttons, hats):
    """Нажатые сейчас кнопки и D-pad (чтобы узнать, какая кнопка руля какая)."""
    out = ["btn%d" % n for n, p in enumerate(buttons) if p]
    for n, h in enumerate(hats):
        out += ["hat%d%s" % (n, k) for k, d in HAT_DIRS.items() if tuple(h) == d]
    return out


# ----------------------------------------------------------------------
# Переключение профилей кнопкой руля или клавишей (глобально, игра в фокусе)
# ----------------------------------------------------------------------
def cycle_profile(cfg, step):
    names = list(cfg["profiles"])
    i = names.index(cfg["current"]) if cfg["current"] in names else 0
    return names[(i + step) % len(names)]


def switch_inputs(cfg):
    """Входы руля, занятые переключением профилей: в привязках профиля они не срабатывают."""
    return {s["input"] for s in cfg["switch"].values() if s.get("input")}


class Switcher(object):
    """Ловит момент нажатия (фронт) кнопки руля / клавиши переключения. poll() -> +1, -1 или 0."""

    def __init__(self):
        self.prev = {}

    def poll(self, cfg, axes, buttons, hats, key_down):
        step = 0
        for name, d in (("next", 1), ("prev", -1)):
            s = cfg["switch"][name]
            for kind in ("input", "key"):
                v = s.get(kind)
                now = bool(v) and (Engine._active({"input": v}, False, axes, buttons, hats) if kind == "input"
                                   else key_down(v))
                if now and not self.prev.get((name, kind)) and not step:
                    step = d
                self.prev[(name, kind)] = now
        return step


# ----------------------------------------------------------------------
# Надпись поверх игры (как в X52 Launcher)
# ----------------------------------------------------------------------
OVERLAY_DEFAULT = {"enabled": True, "mode": "change", "seconds": 3, "position": "top-right", "size": 22,
                   "color": "#33ff99"}
OVERLAY_POS = {"top-left": "Сверху слева", "top-center": "Сверху по центру", "top-right": "Сверху справа",
               "bottom-left": "Снизу слева", "bottom-right": "Снизу справа"}


def sanitize_overlay(o):
    o = o if isinstance(o, dict) else {}
    d = OVERLAY_DEFAULT

    def num(k, lo, hi):
        v = o.get(k)
        return max(lo, min(hi, int(v))) if isinstance(v, (int, float)) and not isinstance(v, bool) else d[k]
    col = o.get("color")
    return {"enabled": bool(o.get("enabled", d["enabled"])),
            "mode": o.get("mode") if o.get("mode") in ("change", "always") else d["mode"],
            "seconds": num("seconds", 1, 30), "size": num("size", 10, 72),
            "position": o.get("position") if o.get("position") in OVERLAY_POS else d["position"],
            "color": col if isinstance(col, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", col) else d["color"]}


class GameOverlay(object):
    """Прозрачное окно поверх всех: клики проходят насквозь, фокус у игры не забирает.
    Окно не прячется, «скрыть» = полная прозрачность (иначе Windows может отнять фокус у игры)."""
    KEY = "#010203"

    def __init__(self, root):
        import tkinter as tk
        self.tk = tk
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=self.KEY)
        try:
            self.win.attributes("-transparentcolor", self.KEY)    # только Windows
        except tk.TclError:
            pass
        self.lbl = tk.Label(self.win, text="", bg=self.KEY, fg="#33ff99", font=("Segoe UI", 22, "bold"),
                            padx=10, pady=4)
        self.lbl.pack()
        self.alpha = 0.0
        self._set_alpha(0.0)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.update_idletasks()
        self._clickthrough()
        self._hide_job = None
        self.sticky = False
        self.text = ""
        self._keep_on_top()

    def _hwnd(self):
        try:
            return int(self.win.wm_frame(), 16)
        except (self.tk.TclError, ValueError):
            return None

    def _clickthrough(self):
        if not IS_WIN:
            return
        try:
            import ctypes
            u32 = ctypes.WinDLL("user32")
            h = self._hwnd()
            if h:
                u32.GetWindowLongW.restype = ctypes.c_long
                ex = u32.GetWindowLongW(h, -20)                   # GWL_EXSTYLE
                # LAYERED | TRANSPARENT (клики насквозь) | TOOLWINDOW (нет в панели задач) | NOACTIVATE
                u32.SetWindowLongW(h, -20, ex | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000)
        except Exception:  # noqa
            pass

    def _topmost(self):
        if not IS_WIN:
            return
        try:
            import ctypes
            h = self._hwnd()
            if h:   # HWND_TOPMOST; SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                ctypes.WinDLL("user32").SetWindowPos(h, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:  # noqa
            pass

    def _keep_on_top(self):
        if self.alpha > 0:
            self._topmost()     # игра могла перекрыть надпись
        self.root.after(2000, self._keep_on_top)

    def _set_alpha(self, a):
        self.alpha = a
        try:
            self.win.attributes("-alpha", a)
        except self.tk.TclError:
            pass

    def show(self, text, o, sticky):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self.text, self.sticky = text, sticky
        self.lbl.configure(text=text, fg=o["color"], font=("Segoe UI", o["size"], "bold"))
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        m = 24
        x = {"left": m, "center": (sw - w) // 2, "right": sw - w - m}[o["position"].split("-")[1]]
        y = m if o["position"].startswith("top") else sh - h - m - 40
        self.win.geometry("+%d+%d" % (x, y))
        self._set_alpha(0.9)
        self._topmost()
        if not sticky:
            self._hide_job = self.root.after(o["seconds"] * 1000, self.hide)

    def hide(self):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
        self._hide_job = None
        self.sticky = False
        self._set_alpha(0.0)


# ----------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------
def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "WheelLauncher")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")


def sanitize_config(cfg):
    cfg = cfg if isinstance(cfg, dict) else {}
    profiles = {}
    for name, bl in (cfg.get("profiles") or {}).items():
        if isinstance(name, str) and name.strip() and isinstance(bl, list):
            profiles[name] = [{"input": b["input"], "key": b["key"], "threshold": int(b.get("threshold", 30)),
                               "label": str(b.get("label", ""))}
                              for b in bl if isinstance(b, dict) and isinstance(b.get("input"), str)
                              and isinstance(b.get("key"), str)]
    if not profiles:
        profiles = {"Forza Horizon": [], "SnowRunner": []}
    sw = cfg.get("switch") if isinstance(cfg.get("switch"), dict) else {}
    switch = {}
    for n in ("next", "prev"):
        s = sw.get(n) if isinstance(sw.get(n), dict) else {}
        switch[n] = {"input": s.get("input") if isinstance(s.get("input"), str) else None,
                     "key": s.get("key") if s.get("key") in KEYS else None}
    cur = cfg.get("current")
    return {"current": cur if cur in profiles else next(iter(profiles)), "profiles": profiles,
            "switch": switch, "overlay": sanitize_overlay(cfg.get("overlay")),
            "joycpl": bool(cfg.get("joycpl", True)),
            "window": sanitize_window(cfg.get("window")),
            "pads": {n: sanitize_pad((cfg.get("pads") or {}).get(n)) for n in profiles}}


PROFILE_FILE = "wheel_launcher_profile"


def export_profile(path, name, bindings, pad=None):
    """Сохранить один профиль в файл .json (можно отдать другу или перенести на другой ПК)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"format": PROFILE_FILE, "name": name, "bindings": bindings, "pad": pad}, f,
                  ensure_ascii=False, indent=2)


def import_profile(path):
    """Прочитать профиль из файла. Возвращает (имя, привязки, настройки геймпада) или бросает ValueError."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError("файл не читается: %s" % e)
    if not isinstance(d, dict) or d.get("format") != PROFILE_FILE or not isinstance(d.get("name"), str):
        raise ValueError("это не файл профиля Wheel Launcher")
    prof = sanitize_config({"profiles": {d["name"]: d.get("bindings")}})["profiles"]
    if d["name"] not in prof:
        raise ValueError("в файле нет привязок")
    return d["name"], prof[d["name"]], sanitize_pad(d.get("pad"))


def unique_name(name, existing):
    n, i = name, 2
    while n in existing:
        n, i = "%s (%d)" % (name, i), i + 1
    return n


MIN_WIN = (700, 460)


def sanitize_window(o):
    """Сохранённые размер/положение окна: {"w","h","x","y","zoomed"} или None."""
    if not isinstance(o, dict):
        return None

    def num(k, lo, hi):
        v = o.get(k)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi else None
    w, h = num("w", MIN_WIN[0], 10000), num("h", MIN_WIN[1], 10000)
    if w is None or h is None:
        return None
    return {"w": w, "h": h, "x": num("x", -20000, 20000), "y": num("y", -20000, 20000), "zoomed": bool(o.get("zoomed"))}


def window_geometry(win, sw, sh):
    """Строка geometry для Tk: размер не больше экрана, положение — только если окно остаётся на экране."""
    w, h = min(win["w"], sw), min(win["h"], sh)
    x, y = win["x"], win["y"]
    if x is None or y is None or x + w < 100 or y + h < 100 or x > sw - 100 or y > sh - 100:
        return "%dx%d" % (w, h)
    return "%dx%d+%d+%d" % (w, h, x, y)


def load_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            return sanitize_config(json.load(f))
    except (OSError, ValueError):
        return sanitize_config(None)


def save_config(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def make_key_down():
    """Опрос клавиатуры, когда в фокусе игра (GetAsyncKeyState). Не Windows — всегда «не нажата»."""
    if not IS_WIN:
        return lambda name: False
    import ctypes
    gaks = ctypes.WinDLL("user32").GetAsyncKeyState
    gaks.restype = ctypes.c_short
    return lambda name: bool(gaks(VK[name]) & 0x8000)


# ----------------------------------------------------------------------
# joy.cpl: «Свойства» руля открыты за краем экрана (как в X52 Launcher). Win32 через ctypes, без PowerShell.
# ----------------------------------------------------------------------
JOYCPL_ERRORS = {"nowheel": "руль не найден в списке игровых устройств (joy.cpl)",
                 "nobtn": "кнопка «Свойства» не найдена"}
_W32 = None


def _w32():
    global _W32
    if _W32 is None:
        import ctypes
        from ctypes import wintypes as W
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        enum_proc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        for fn, args, res in (
                (u32.EnumWindows, (enum_proc, W.LPARAM), W.BOOL),
                (u32.EnumChildWindows, (W.HWND, enum_proc, W.LPARAM), W.BOOL),
                (u32.GetClassNameW, (W.HWND, W.LPWSTR, ctypes.c_int), ctypes.c_int),
                (u32.GetWindowTextW, (W.HWND, W.LPWSTR, ctypes.c_int), ctypes.c_int),
                (u32.IsWindowVisible, (W.HWND,), W.BOOL),
                (u32.IsWindow, (W.HWND,), W.BOOL),
                (u32.GetWindowRect, (W.HWND, ctypes.POINTER(W.RECT)), W.BOOL),
                (u32.GetWindowThreadProcessId, (W.HWND, ctypes.POINTER(W.DWORD)), W.DWORD),
                (u32.SendMessageW, (W.HWND, W.UINT, ctypes.c_size_t, ctypes.c_ssize_t), ctypes.c_ssize_t),
                (u32.PostMessageW, (W.HWND, W.UINT, ctypes.c_size_t, ctypes.c_ssize_t), W.BOOL),
                (u32.SetWindowPos, (W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    W.UINT), W.BOOL),
                (k32.OpenProcess, (W.DWORD, W.BOOL, W.DWORD), W.HANDLE),
                (k32.VirtualAllocEx, (W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD, W.DWORD),
                 ctypes.c_void_p),
                (k32.VirtualFreeEx, (W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD), W.BOOL),
                (k32.WriteProcessMemory, (W.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
                                          ctypes.c_void_p), W.BOOL),
                (k32.ReadProcessMemory, (W.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
                                         ctypes.c_void_p), W.BOOL),
                (k32.CloseHandle, (W.HANDLE,), W.BOOL)):
            fn.argtypes, fn.restype = args, res
        _W32 = (ctypes, W, u32, k32, enum_proc)
    return _W32


def _windows(parent=None):
    ctypes, W, u32, k32, enum_proc = _w32()
    res = []
    cb = enum_proc(lambda h, l: res.append(h) or True)
    if parent is None:
        u32.EnumWindows(cb, 0)
    else:
        u32.EnumChildWindows(parent, cb, 0)
    return res


def _wclass(h):
    ctypes, W, u32, k32, _ = _w32()
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, buf, 256)
    return buf.value


def _wtext(h):
    ctypes, W, u32, k32, _ = _w32()
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(h, buf, 512)
    return buf.value


def _wpid(h):
    ctypes, W, u32, k32, _ = _w32()
    pid = W.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def _lv_remote(lv, select=-1):
    """Строки SysListView32 чужого процесса (или выделить строку select): UI Automation видит их не у всех.
    LVITEMW кладём в память процесса списка (той же разрядности, что и мы), текст — по смещению 0x100."""
    ctypes, W, u32, k32, _ = _w32()
    ptr = ctypes.sizeof(ctypes.c_void_p)

    def item(state, text):
        it = bytearray(88 if ptr == 8 else 60)
        struct.pack_into("<ii", it, 12, state, state)              # state, stateMask
        off = 24 if ptr == 8 else 20                               # pszText
        struct.pack_into("<Qi" if ptr == 8 else "<Ii", it, off, text, 512)   # + cchTextMax
        return bytes(it)

    pid = _wpid(lv)
    proc = k32.OpenProcess(0x38, False, pid)                       # VM_OPERATION | VM_READ | VM_WRITE
    if not proc:
        raise OSError(f"OpenProcess {pid}")
    mem = k32.VirtualAllocEx(proc, None, 0x1000, 0x3000, 0x04)
    try:
        if not mem:
            raise OSError(f"VirtualAllocEx {pid}")
        if select >= 0:                                            # LVM_SETITEMSTATE: выделить и сфокусировать
            it = item(3, 0)
            k32.WriteProcessMemory(proc, mem, it, len(it), None)
            u32.SendMessageW(lv, 0x102B, select, mem)
            return []
        res = []
        for i in range(u32.SendMessageW(lv, 0x1004, 0, 0)):        # LVM_GETITEMCOUNT
            it = item(0, mem + 0x100)
            k32.WriteProcessMemory(proc, mem, it, len(it), None)
            n = u32.SendMessageW(lv, 0x1073, i, mem)               # LVM_GETITEMTEXTW
            buf = ctypes.create_string_buffer(n * 2)
            k32.ReadProcessMemory(proc, mem + 0x100, buf, n * 2, None)
            res.append(buf.raw.decode("utf-16-le"))
        return res
    finally:
        if mem:
            k32.VirtualFreeEx(proc, mem, 0, 0x8000)
        k32.CloseHandle(proc)


def _away(h):
    _w32()[2].SetWindowPos(h, None, -32000, -32000, 0, 0, 0x15)


def open_joycpl(device="", cancel=None):
    """Открыть «Свойства» руля в joy.cpl за краем экрана. (pid joy.cpl или None, сообщение).
    Драйвер части рулей отдаёт кнопки/оси играм только пока эти «Свойства» открыты."""
    if not IS_WIN:
        return None, "доступно только в Windows"
    try:
        u32 = _w32()[2]
        # окна joy.cpl, открытые до нас (вручную), не трогаем
        before = {h for h in _windows() if _wclass(h) == "#32770"}
        p = subprocess.Popen(["rundll32.exe", "shell32.dll,Control_RunDLL", "joy.cpl"])
    except Exception as e:  # noqa
        return None, str(e)
    dev = device.lower().strip()

    def pick(names):
        for i, n in enumerate(names):
            nl = n.lower()
            if (dev and (dev in nl or nl in dev)) or "wheel" in nl:
                return i
        return 0 if len(names) == 1 else None      # единственное устройство — берём его

    def find_wheel():
        # окно ищем по содержимому (список устройств), а не по PID: диалог может быть в другом процессе
        for w in _windows():
            if w in before or _wclass(w) != "#32770" or not u32.IsWindowVisible(w):
                continue
            for lv in _windows(w):
                if _wclass(lv) != "SysListView32":
                    continue
                try:
                    names = _lv_remote(lv)
                except OSError:
                    continue
                i = pick(names)
                if i is not None:
                    return w, lv, i
        return None

    clicked = False
    dlg_pid = None
    try:
        found = None
        for _ in range(150):
            found = find_wheel()
            if found or (cancel and cancel()):
                break
            time.sleep(0.1)
        if not found:
            raise RuntimeError("nowheel")
        main, lv, idx = found
        dlg_pid = _wpid(main)
        _lv_remote(lv, idx)
        time.sleep(0.3)
        btn = next((c for c in _windows(main) if _wclass(c) == "Button"
                    and re.search("Свойства|Properties", _wtext(c).replace("&", ""))), None)
        if not btn:
            raise RuntimeError("nobtn")
        # BM_CLICK через PostMessage: SendMessage ждал бы закрытия модального окна свойств
        u32.PostMessageW(btn, 0xF5, 0, 0)
        clicked = True
        sheets = []
        for _ in range(150):
            sheets = [w for w in _windows() if w != main and _wpid(w) == dlg_pid and u32.IsWindowVisible(w)]
            if sheets or (cancel and cancel()):
                break
            time.sleep(0.1)
        _JOY_HWNDS[:] = [main] + sheets
        _away(main)
        for h in sheets:
            _away(h)
        time.sleep(0.5)     # и ещё раз — окно могло встать по центру уже после нас
        for h in sheets:
            _away(h)
    except Exception as e:  # noqa
        # после нажатия «Свойства» процесс не убиваем: принудительное завершение ломает руль до переподключения
        if not clicked:
            p.kill()
        err = e.args[0] if isinstance(e, RuntimeError) and e.args else str(e)
        return None, JOYCPL_ERRORS.get(err, err)
    if not sheets:
        return dlg_pid, "окно свойств не найдено"
    return dlg_pid, "свойства руля открыты (окно за краем экрана)"


_JOY_HWNDS = []     # окна joy.cpl, которые открыли мы (на случай, если pid окажется не тот)
_AWAY = -30000      # окна joy.cpl уводятся за экран на -32000: так узнаём «хвосты» прошлого запуска


def _visible_windows(pid):
    u32 = _w32()[2]
    return [w for w in _windows() if _wpid(w) == pid and u32.IsWindowVisible(w)]


def close_joycpl(pid):
    """Закрыть окна joy.cpl. Сначала вежливо (WM_CLOSE: первое закрывает «Свойства», второе — joy.cpl): после
    принудительного завершения страницы свойств драйвер может перестать отдавать руль до переподключения.
    Если окна не закрылись — завершаем процесс."""
    if not IS_WIN:
        return
    try:
        u32 = _w32()[2]
        for _ in range(3):
            ws = set(_visible_windows(pid)) if pid else set()
            ws |= {w for w in _JOY_HWNDS if u32.IsWindow(w)}
            if not ws:
                break
            for w in ws:
                u32.PostMessageW(w, 0x0010, 0, 0)               # WM_CLOSE
            for _ in range(15):
                time.sleep(0.1)
                if not any(u32.IsWindow(w) and u32.IsWindowVisible(w) for w in ws):
                    break
        _JOY_HWNDS[:] = [w for w in _JOY_HWNDS if u32.IsWindow(w)]
        if pid:
            for force in ([], ["/F"]):      # процесс мог остаться без окон — добиваем
                r = subprocess.run(["taskkill", "/PID", str(pid), "/T"] + force, capture_output=True,
                                   timeout=10, creationflags=0x08000000)
                if r.returncode == 128:     # процесса уже нет
                    break
                time.sleep(0.3)
    except Exception:  # noqa
        pass


def close_stale_joycpl():
    """Окна joy.cpl, оставшиеся за экраном от прошлого запуска (программу закрыли аварийно): закрыть."""
    if not IS_WIN:
        return
    try:
        ctypes, W, u32, _k, _ = _w32()
        pids = set()
        for w in _windows():
            if _wclass(w) == "#32770" and u32.IsWindowVisible(w):
                r = W.RECT()
                if u32.GetWindowRect(w, ctypes.byref(r)) and r.left <= _AWAY and r.top <= _AWAY:
                    pids.add(_wpid(w))
        for pid in pids:
            close_joycpl(pid)
    except Exception:  # noqa
        pass




# ----------------------------------------------------------------------
# Окно
# ----------------------------------------------------------------------
def main():
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"  # руль читается, пока окно игры в фокусе
    import tkinter as tk
    from tkinter import ttk, simpledialog, messagebox, colorchooser, filedialog
    import pygame
    pygame.display.init()
    pygame.joystick.init()

    path = config_path()
    cfg = load_config(path)
    output = Output()
    engine = Engine(output)
    switcher = Switcher()
    key_down = make_key_down()
    st = {"joy": None, "running": False, "learn": None, "hot": set(), "pad_on": False, "pad_vals": (0, 0, 0)}

    root = tk.Tk()
    root.title("%s %s" % (APP_NAME, APP_VERSION))
    try:
        root.iconbitmap(os.path.join(RES_DIR, "wheel_launcher.ico"))
    except tk.TclError:
        pass
    root.minsize(*MIN_WIN)
    root.geometry(window_geometry(cfg["window"], root.winfo_screenwidth(), root.winfo_screenheight())
                  if cfg["window"] else "780x580")
    if cfg["window"] and cfg["window"]["zoomed"]:
        try:
            root.state("zoomed")
        except tk.TclError:
            pass
    overlay = GameOverlay(root)

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    dev_var = tk.StringVar(value="Руль не найден")
    ttk.Label(top, textvariable=dev_var).pack(anchor="w")
    live_var = tk.StringVar()
    ttk.Label(top, textvariable=live_var, font=("Consolas", 9)).pack(anchor="w")
    joy_var = tk.BooleanVar(value=cfg["joycpl"])
    jc = {"pid": None, "msg": tk.StringVar()}

    def start_joycpl():
        if not IS_WIN:
            jc["msg"].set("joy.cpl: только в Windows")
            return
        jc["msg"].set("joy.cpl: открываю «Свойства» руля…")

        def task():
            close_joycpl(jc["pid"])
            close_stale_joycpl()
            pid, msg = None, ""
            for _ in range(3):    # после включения ПК список устройств заполняется не сразу
                pid, msg = open_joycpl(st["joy"].get_name() if st["joy"] else "", lambda: st.get("closing"))
                if pid or st.get("closing"):
                    break
                for _ in range(50):
                    if st.get("closing"):
                        break
                    time.sleep(0.1)
            jc["pid"] = pid
            jc["msg"].set(("joy.cpl: " if pid else "joy.cpl: ошибка — ") + msg)
        jc["thread"] = threading.Thread(target=task, daemon=True)
        jc["thread"].start()

    def on_joycpl():
        cfg["joycpl"] = bool(joy_var.get())
        save()
        if cfg["joycpl"]:
            start_joycpl()
        else:
            close_joycpl(jc["pid"])
            jc["pid"] = None
            jc["msg"].set("joy.cpl: закрыт")

    ttk.Checkbutton(top, variable=joy_var, command=on_joycpl, text=(
        "Открывать «Свойства» руля (joy.cpl) при запуске — без этого игры могут не видеть руль")).pack(anchor="w")
    ttk.Label(top, textvariable=jc["msg"]).pack(anchor="w")
    vg_var = tk.StringVar()
    vg_row = ttk.Frame(top)
    vg_row.pack(anchor="w", fill="x")
    vg_lbl = tk.Label(vg_row, textvariable=vg_var, anchor="w")
    vg_lbl.pack(side="left")
    vg_btn = ttk.Button(vg_row, text="Скачать драйвер", command=lambda: __import__("webbrowser").open(VIGEM_URL))

    def update_vigem():
        text, ok = vigem_status(vigem_installed(), pad_settings()["enabled"])
        vg_var.set(text)
        vg_lbl.config(fg="#1a8f3c" if ok else "#d12b2b")
        if ok:
            vg_btn.pack_forget()
        else:
            vg_btn.pack(side="left", padx=6)
    now_var = tk.StringVar(value="Нажато на руле: —")
    ttk.Label(top, textvariable=now_var).pack(anchor="w")

    prof = ttk.Frame(root, padding=(8, 0))
    prof.pack(fill="x")
    ttk.Label(prof, text="Профиль:").pack(side="left")
    prof_var = tk.StringVar(value=cfg["current"])
    combo = ttk.Combobox(prof, textvariable=prof_var, state="readonly", width=24)
    combo.pack(side="left", padx=4)

    prof2 = ttk.Frame(root, padding=(8, 2, 8, 0))
    prof2.pack(fill="x")

    # нижние панели пакуются раньше списка: при любом размере окна «Старт» и кнопки остаются видны
    sw_var = tk.StringVar()
    ttk.Label(root, textvariable=sw_var, padding=(8, 0, 8, 6)).pack(side="bottom", anchor="w")
    btns2 = ttk.Frame(root, padding=(8, 0, 8, 2))
    btns2.pack(side="bottom", fill="x")
    btns = ttk.Frame(root, padding=(8, 4))
    btns.pack(side="bottom", fill="x")
    run_btn = ttk.Button(btns, text="Старт", width=12)
    run_btn.pack(side="right")

    tree = ttk.Treeview(root, columns=("in", "label", "key", "thr"), show="headings", height=8)
    for c, t, w in (("in", "Вход руля", 170), ("label", "Подпись (за что отвечает)", 260),
                    ("key", "Клавиша", 100), ("thr", "Порог оси, %", 100)):
        tree.heading(c, text=t)
        tree.column(c, width=w)
    tree.tag_configure("hot", background="#1e6fd9", foreground="white")
    tree.pack(fill="both", expand=True, padx=8, pady=8)


    def bindings():
        return cfg["profiles"][cfg["current"]]

    def pad_settings(name=None):
        return cfg["pads"].setdefault(name or cfg["current"], dict(PAD_DEFAULT))

    def save():
        save_config(path, cfg)

    def sw_text(s):
        parts = [input_label(s["input"])] if s["input"] else []
        parts += [key_label(s["key"])] if s["key"] else []
        return " / ".join(parts) or "не назначено"

    def refresh():
        combo["values"] = list(cfg["profiles"])
        prof_var.set(cfg["current"])
        tree.delete(*tree.get_children())
        busy = switch_inputs(cfg)
        pbusy = pad_busy(pad_settings())
        for i, b in enumerate(bindings()):
            axis = b["input"].startswith("axis")
            lab = b["label"] + ("  (занято переключением профилей)" if b["input"] in busy else "") + \
                ("  (занято виртуальным геймпадом)" if b["input"] in pbusy else "")
            tree.insert("", "end", iid=str(i), values=(input_label(b["input"]), lab, key_label(b["key"]),
                                                       b["threshold"] if axis else "—"))
        st["hot"] = set()
        if "update_vigem" in st:
            st["update_vigem"]()
        sw_var.set("Следующий профиль: %s    Предыдущий: %s" % (sw_text(cfg["switch"]["next"]),
                                                               sw_text(cfg["switch"]["prev"])))

    def show_overlay():
        o = cfg["overlay"]
        if not o["enabled"] or (o["mode"] == "always" and not st["running"]):
            overlay.hide()
        else:
            overlay.show(cfg["current"], o, o["mode"] == "always")

    def switch_profile(name):
        engine.release_all()
        cfg["current"] = name
        save()
        refresh()
        show_overlay()

    st["update_vigem"] = update_vigem

    def pad_check():
        update_vigem()
        """Нужен ли в профиле виртуальный геймпад и создаётся ли он; иначе объясняем, что делать."""
        if not (pad_settings()["enabled"] or any(b["key"] in PAD_BUTTONS for b in bindings())):
            return
        if output.pad.ensure():
            return
        if messagebox.askyesno(APP_NAME, "Не удалось создать виртуальный геймпад:\n%s\n\nСкорее всего не установлен драйвер "
                               "ViGEmBus. Установите его (откроется официальная страница загрузки: файл ViGEmBus_…_x64_x86_arm64.exe), "
                               "перезагрузите ПК и запустите программу снова.\n\nОткрыть страницу загрузки?" % output.pad.err):
            import webbrowser
            webbrowser.open(VIGEM_URL)

    def stop():
        st["running"] = False
        st["pad_on"] = False
        engine.release_all()
        output.pad.reset()
        run_btn.config(text="Старт")
        if overlay.sticky:
            overlay.hide()

    def toggle():
        if st["running"]:
            stop()
        elif st["joy"] is None:
            messagebox.showwarning(APP_NAME, "Руль не найден. Подключите его и перезапустите программу.")
        else:
            st["running"] = True
            run_btn.config(text="Стоп")
            show_overlay()
            pad_check()

    combo.bind("<<ComboboxSelected>>", lambda _=None: switch_profile(prof_var.get()))

    def new_profile():
        name = simpledialog.askstring(APP_NAME, "Название нового профиля:", parent=root)
        name = (name or "").strip()
        if not name:
            return
        if name in cfg["profiles"]:
            messagebox.showwarning(APP_NAME, "Профиль «%s» уже есть." % name)
            return
        copy_ = messagebox.askyesno(APP_NAME, "Скопировать назначения из профиля «%s»?\n"
                                    "«Нет» — новый профиль будет пустым." % cfg["current"])
        cfg["profiles"][name] = copy.deepcopy(bindings()) if copy_ else []
        cfg["pads"][name] = copy.deepcopy(pad_settings()) if copy_ else dict(PAD_DEFAULT)
        switch_profile(name)

    def rename_profile():
        old = cfg["current"]
        name = (simpledialog.askstring(APP_NAME, "Новое название профиля:", initialvalue=old, parent=root) or "").strip()
        if not name or name == old:
            return
        if name in cfg["profiles"]:
            messagebox.showwarning(APP_NAME, "Профиль «%s» уже есть." % name)
            return
        cfg["profiles"] = {(name if k == old else k): v for k, v in cfg["profiles"].items()}
        cfg["pads"] = {(name if k == old else k): v for k, v in cfg["pads"].items()}
        switch_profile(name)

    def del_profile():
        if len(cfg["profiles"]) < 2:
            messagebox.showinfo(APP_NAME, "Это единственный профиль.")
        elif messagebox.askyesno(APP_NAME, "Удалить профиль «%s»?" % cfg["current"]):
            nxt = cycle_profile(cfg, 1)
            del cfg["profiles"][cfg["current"]]
            cfg["pads"].pop(cfg["current"], None)
            switch_profile(nxt)

    def save_profile():
        f = filedialog.asksaveasfilename(parent=root, title="Сохранить профиль в файл", defaultextension=".json",
                                         initialfile=cfg["current"], filetypes=[("Профиль Wheel Launcher", "*.json")])
        if f:
            export_profile(f, cfg["current"], bindings(), pad_settings())

    def load_profile():
        f = filedialog.askopenfilename(parent=root, title="Добавить профиль из файла",
                                       filetypes=[("Профиль Wheel Launcher", "*.json")])
        if not f:
            return
        try:
            name, bl, pad = import_profile(f)
        except ValueError as e:
            messagebox.showwarning(APP_NAME, "Не удалось добавить профиль: %s" % e)
            return
        name = unique_name(name, cfg["profiles"])
        cfg["profiles"][name] = bl
        cfg["pads"][name] = pad
        switch_profile(name)

    for t, f in (("Новый", new_profile), ("Переименовать", rename_profile), ("Удалить", del_profile)):
        ttk.Button(prof, text=t, command=f).pack(side="left", padx=2)
    for t, f in (("Сохранить в файл…", save_profile), ("Добавить из файла…", load_profile)):
        ttk.Button(prof2, text=t, command=f).pack(side="left", padx=2)

    def read_joy():
        j = st["joy"]
        pygame.event.pump()
        return ([j.get_axis(i) for i in range(j.get_numaxes())],
                [j.get_button(i) for i in range(j.get_numbuttons())],
                [j.get_hat(i) for i in range(j.get_numhats())])

    def learn_wheel(win, msg, done):
        """Ждать, пока пользователь задействует руль; done(input) вызывается из tick()."""
        axes, _, _ = read_joy()
        st["learn"] = {"base": list(axes), "msg": msg, "done": done}
        win.bind("<Destroy>", lambda e: st.update(learn=None) if e.widget is win else None, add="+")

    def ask_label(b):
        v = simpledialog.askstring(APP_NAME, "Подпись для «%s» (например: Ручник, Передача вверх):"
                                   % input_label(b["input"]), initialvalue=b["label"], parent=root)
        if v is not None:
            b["label"] = v.strip()
            save()
            refresh()

    def key_picker(parent, on_pick, current=None):
        """Выпадающий список всех клавиш + кнопка «Назначить»."""
        f = ttk.Frame(parent)
        f.combo = ttk.Combobox(f, values=[key_label(k) for k in PICK_ORDER], state="readonly", width=34, height=20)
        if current in KEYS or current in PAD_BUTTONS:
            f.combo.set(key_label(current))
        f.combo.pack(side="left")
        ttk.Button(f, text="Назначить", command=lambda: f.combo.get() in KEY_BY_LABEL
                   and on_pick(KEY_BY_LABEL[f.combo.get()])).pack(side="left", padx=6)
        return f

    def edit_key():
        b = selected()
        if not b:
            return
        win = tk.Toplevel(root)
        win.title("Клавиша для: %s" % input_label(b["input"]))
        win.grab_set()
        ttk.Label(win, text="Выберите клавишу в списке или нажмите её на клавиатуре.", padding=10).pack()
        f = None

        def pick(key):
            stop()
            b["key"] = key
            save()
            refresh()
            win.destroy()
        f = key_picker(win, pick, b["key"])
        f.pack(padx=10, pady=(0, 10))

        def on_key(e):
            key = key_from_event(e.keycode, e.keysym)
            if e.widget is not f.combo and key in KEYS:
                pick(key)
        win.bind("<KeyPress>", on_key)

    def add():
        if st["joy"] is None:
            messagebox.showwarning(APP_NAME, "Руль не найден.")
            return
        stop()
        win = tk.Toplevel(root)
        win.title("Новая привязка")
        win.geometry("420x170")
        win.grab_set()
        msg = tk.StringVar(value="1) Поверните руль, нажмите педаль, кнопку или D-pad.\n"
                                 "Руль не трогайте 1 секунду до этого.")
        ttk.Label(win, textvariable=msg, padding=12).pack()
        got = {}

        def on_input(inp):
            got["input"] = inp
            msg.set("Вход: %s\n2) Выберите клавишу в списке или нажмите её на клавиатуре." % input_label(inp))
            picker.pack(padx=12, pady=4)

        def finish(key):
            b = {"input": got["input"], "key": key, "threshold": 30, "label": ""}
            bindings().append(b)
            win.destroy()
            save()
            refresh()
            ask_label(b)

        picker = key_picker(win, finish)

        def on_key(e):
            if "input" not in got or e.widget is picker.combo:
                return
            key = key_from_event(e.keycode, e.keysym)
            if key not in KEYS:
                msg.set("Эту клавишу пока нельзя назначить: %s\nНажмите другую." % e.keysym)
                return
            finish(key)

        win.bind("<KeyPress>", on_key)
        learn_wheel(win, msg, on_input)
        win.focus_force()

    def selected():
        sel = tree.selection()
        return bindings()[tree.index(sel[0])] if sel else None

    def delete():
        b = selected()
        if b:
            stop()
            bindings().remove(b)
            save()
            refresh()

    def edit_label():
        b = selected()
        if b:
            ask_label(b)

    def edit_threshold():
        b = selected()
        if not b or not b["input"].startswith("axis"):
            return
        v = simpledialog.askinteger(APP_NAME, "Порог срабатывания оси, % (5–95):",
                                    initialvalue=b["threshold"], minvalue=5, maxvalue=95)
        if v:
            b["threshold"] = v
            save()
            refresh()

    tree.bind("<Double-1>", lambda e: edit_label())

    def switch_dialog():
        if st["joy"] is None:
            messagebox.showwarning(APP_NAME, "Руль не найден.")
            return
        stop()
        win = tk.Toplevel(root)
        win.title("Переключение профилей")
        win.grab_set()
        msg = tk.StringVar(value="Работает, когда нажат «Старт» (и когда в фокусе игра).\n"
                                 "Профили идут по кругу в порядке списка.")
        ttk.Label(win, textvariable=msg, padding=10).grid(row=0, column=0, columnspan=5, sticky="w")
        waiting = {"key": None}
        rows = {}

        def show_rows():
            for n, v in rows.items():
                v.set(sw_text(cfg["switch"][n]))

        def set_wheel(n):
            msg.set("Нажмите кнопку руля (или D-pad) для: %s" % ("следующий" if n == "next" else "предыдущий"))

            def done(inp):
                cfg["switch"][n]["input"] = inp
                save()
                msg.set("Назначено: %s" % input_label(inp))
                show_rows()
                refresh()
            learn_wheel(win, msg, done)

        def set_key(n):
            waiting["key"] = n
            msg.set("Нажмите клавишу клавиатуры (лучше ту, что не занята в игре, например F9).")
            win.focus_force()

        def on_key(e):
            n = waiting["key"]
            if not n:
                return
            key = key_from_event(e.keycode, e.keysym)
            if key not in KEYS:
                msg.set("Эту клавишу нельзя назначить: %s" % e.keysym)
                return
            cfg["switch"][n]["key"] = key
            waiting["key"] = None
            save()
            msg.set("Назначено: %s" % key_label(key))
            show_rows()
            refresh()

        def clear(n):
            cfg["switch"][n] = {"input": None, "key": None}
            save()
            show_rows()
            refresh()

        for r, (n, t) in enumerate((("next", "Следующий профиль"), ("prev", "Предыдущий профиль")), start=1):
            rows[n] = tk.StringVar()
            ttk.Label(win, text=t + ":").grid(row=r, column=0, sticky="w", padx=8, pady=4)
            ttk.Label(win, textvariable=rows[n], width=24).grid(row=r, column=1, sticky="w")
            ttk.Button(win, text="Кнопка руля…", command=lambda n=n: set_wheel(n)).grid(row=r, column=2, padx=2)
            ttk.Button(win, text="Клавиша…", command=lambda n=n: set_key(n)).grid(row=r, column=3, padx=2)
            ttk.Button(win, text="Сбросить", command=lambda n=n: clear(n)).grid(row=r, column=4, padx=(2, 8))
        ttk.Button(win, text="Закрыть", command=win.destroy).grid(row=3, column=4, pady=8, padx=8)
        win.bind("<KeyPress>", on_key)
        show_rows()
        win.focus_force()

    def pad_dialog():
        if st["joy"] is None:
            messagebox.showwarning(APP_NAME, "Руль не найден.")
            return
        stop()
        pd = pad_settings()
        win = tk.Toplevel(root)
        win.title("Виртуальный геймпад — профиль «%s»" % cfg["current"])
        win.grab_set()
        en, inv = tk.BooleanVar(value=pd["enabled"]), tk.BooleanVar(value=pd["invert"])
        dz, rg = tk.IntVar(value=pd["deadzone"]), tk.IntVar(value=pd["range"])
        ax_var, thr_var, brk_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        live, msg = tk.StringVar(), tk.StringVar()
        st["pad_live"] = live
        win.bind("<Destroy>", lambda e: st.update(pad_live=None) if e.widget is win else None, add="+")
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both")

        def show():
            ax_var.set("Ось %s" % (AXIS_NAMES[pd["axis"]] if pd["axis"] < len(AXIS_NAMES) else pd["axis"]))
            thr_var.set(input_label(pd["throttle"]) if pd["throttle"] else "не назначено")
            brk_var.set(input_label(pd["brake"]) if pd["brake"] else "не назначено")
        show()

        def learn_axis():
            msg.set("Поверните руль в сторону (1 с до этого не трогайте).")

            def done(inp):
                if inp.startswith("axis"):
                    pd["axis"] = int(inp[4:-1])
                    msg.set("Ось руля назначена.")
                else:
                    msg.set("Это не ось. Поверните руль.")
                show()
            learn_wheel(win, msg, done)

        def learn_pedal(kind):
            msg.set("Нажмите педаль или кнопку (1 с до этого не трогайте руль и педали).")

            def done(inp):
                pd[kind] = inp
                msg.set("Назначено: %s" % input_label(inp))
                show()
            learn_wheel(win, msg, done)

        def clear(kind):
            pd[kind] = None
            show()

        ttk.Checkbutton(f, text="Включить виртуальный геймпад Xbox 360 в этом профиле (руль = левый стик, "
                        "газ = правый триггер, тормоз = левый триггер)", variable=en).grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text="Руль:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(f, textvariable=ax_var, width=20).grid(row=1, column=1, sticky="w")
        ttk.Button(f, text="Определить поворотом…", command=learn_axis).grid(row=1, column=2, columnspan=2, sticky="w")
        ttk.Checkbutton(f, text="Инвертировать поворот", variable=inv).grid(row=2, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="Мёртвая зона в центре, %:").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(f, from_=0, to=30, textvariable=dz, width=5).grid(row=3, column=1, sticky="w")
        ttk.Label(f, text="Полный поворот колёс при, % хода руля:").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(f, from_=10, to=100, textvariable=rg, width=5).grid(row=4, column=1, sticky="w")
        for r, (kind, t, v) in enumerate((("throttle", "Газ:", thr_var), ("brake", "Тормоз:", brk_var)), start=5):
            ttk.Label(f, text=t).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Label(f, textvariable=v, width=20).grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Назначить…", command=lambda k=kind: learn_pedal(k)).grid(row=r, column=2, padx=2)
            ttk.Button(f, text="Сбросить", command=lambda k=kind: clear(k)).grid(row=r, column=3)
        dlg_vg = tk.Label(f, anchor="w", justify="left", wraplength=480)
        dlg_vg.grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 0))
        vtext, vok = vigem_status(vigem_installed(), pd["enabled"])
        dlg_vg.config(text=vtext, fg="#1a8f3c" if vok else "#d12b2b")
        if not vok:
            ttk.Button(f, text="Скачать драйвер", command=lambda: __import__("webbrowser").open(VIGEM_URL)).grid(
                row=11, column=3, pady=(8, 0))
        ttk.Label(f, textvariable=live, font=("Consolas", 10)).grid(row=7, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Label(f, textvariable=msg, foreground="#1e6fd9").grid(row=8, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text="Назначенные здесь оси и кнопки не нажимают клавиши. Остальные кнопки руля можно\n"
                  "назначать на клавиши или на кнопки геймпада («Добавить» → список клавиш).",
                  foreground="gray").grid(row=9, column=0, columnspan=4, sticky="w", pady=(6, 0))

        def ok():
            try:
                pd.update(deadzone=dz.get(), range=rg.get())
            except tk.TclError:
                pass
            pd.update(enabled=en.get(), invert=inv.get())
            cfg["pads"][cfg["current"]] = sanitize_pad(pd)
            save()
            win.destroy()
            refresh()
            update_vigem()
        ttk.Button(f, text="OK", command=ok).grid(row=10, column=3, sticky="e", pady=(10, 0))

    def overlay_dialog():
        o = dict(cfg["overlay"])
        win = tk.Toplevel(root)
        win.title("Надпись поверх игры")
        win.grab_set()
        en = tk.BooleanVar(value=o["enabled"])
        mode = tk.StringVar(value=o["mode"])
        sec = tk.IntVar(value=o["seconds"])
        size = tk.IntVar(value=o["size"])
        pos = tk.StringVar(value=OVERLAY_POS[o["position"]])
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both")
        ttk.Checkbutton(f, text="Показывать название профиля поверх игры", variable=en).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="При смене профиля, секунд:", value="change", variable=mode).grid(
            row=1, column=0, sticky="w")
        ttk.Spinbox(f, from_=1, to=30, textvariable=sec, width=5).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(f, text="Всегда (пока нажат «Старт»)", value="always", variable=mode).grid(
            row=2, column=0, sticky="w")
        ttk.Label(f, text="Где:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(f, textvariable=pos, values=list(OVERLAY_POS.values()), state="readonly",
                     width=20).grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Label(f, text="Размер шрифта:").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(f, from_=10, to=72, textvariable=size, width=5).grid(row=4, column=1, sticky="w")
        col_lbl = tk.Label(f, text="  Цвет  ", bg=o["color"])
        col_lbl.grid(row=5, column=1, sticky="w", pady=4)

        def pick():
            c = colorchooser.askcolor(o["color"], parent=win)[1]
            if c:
                o["color"] = c
                col_lbl.config(bg=c)
        ttk.Button(f, text="Цвет текста…", command=pick).grid(row=5, column=0, sticky="w")

        def collect():
            try:
                o.update(seconds=sec.get(), size=size.get())
            except tk.TclError:
                pass
            o.update(enabled=en.get(), mode=mode.get(),
                     position={v: k for k, v in OVERLAY_POS.items()}[pos.get()])
            return sanitize_overlay(o)

        def test():
            overlay.show(cfg["current"], collect(), False)

        def ok():
            cfg["overlay"] = collect()
            save()
            win.destroy()
            show_overlay() if st["running"] else overlay.hide()

        ttk.Button(f, text="Проверить", command=test).grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Button(f, text="OK", command=ok).grid(row=6, column=2, sticky="e", pady=(10, 0))

    for row, items in ((btns, (("Добавить", add), ("Удалить", delete), ("Подпись…", edit_label),
                               ("Клавиша…", edit_key), ("Порог оси…", edit_threshold))),
                       (btns2, (("Переключение профилей…", switch_dialog), ("Геймпад…", pad_dialog),
                                ("Надпись поверх игры…", overlay_dialog)))):
        for t, fn in items:
            ttk.Button(row, text=t, command=fn).pack(side="left", padx=2)
    run_btn.config(command=toggle)

    def connect():
        pygame.joystick.quit()
        pygame.joystick.init()
        st["joy"] = None
        for i in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(i)
            j.init()
            st["joy"] = j
            if "wheel" in j.get_name().lower():
                break
        dev_var.set(st["joy"].get_name() if st["joy"] else "Руль не найден")

    def tick():
        if st["joy"] is not None:
            try:
                axes, buttons, hats = read_joy()
            except pygame.error:
                stop()
                connect()
                root.after(500, tick)
                return
            live_var.set("  ".join("%s=%+4d%%" % (AXIS_NAMES[i], round(v * 100)) for i, v in enumerate(axes[:4])))
            pr = pressed_inputs(buttons, hats)
            now_var.set("Нажато на руле: " + (", ".join(input_label(p) for p in pr) or "—"))
            st["pad_vals"] = pad_values(pad_settings(), axes, buttons, hats)
            if st.get("pad_live") is not None:
                v = st["pad_vals"]
                st["pad_live"].set("Руль %+.2f    Газ %.2f    Тормоз %.2f" % v)
            hot = active_rows(bindings(), axes, buttons, hats)
            if hot != st["hot"]:
                for iid in tree.get_children():
                    tree.item(iid, tags=("hot",) if int(iid) in hot else ())
                st["hot"] = hot
            L = st["learn"]
            if L:
                inp = detect_input(L["base"], axes, buttons, hats)
                if inp:
                    st["learn"] = None
                    L["done"](inp)
            if st["running"]:
                step = switcher.poll(cfg, axes, buttons, hats, key_down)
                if step and len(cfg["profiles"]) > 1:
                    switch_profile(cycle_profile(cfg, step))
                pd = pad_settings()
                busy = switch_inputs(cfg) | pad_busy(pd)
                engine.update([b for b in bindings() if b["input"] not in busy], axes, buttons, hats)
                if pd["enabled"]:
                    output.pad.axes(*st["pad_vals"])
                    st["pad_on"] = True
                elif st["pad_on"]:
                    output.pad.reset()
                    st["pad_on"] = False
        root.after(8, tick)

    def remember_window(_=None):
        """Запомнить размер и положение окна (после паузы, чтобы не писать файл на каждый пиксель)."""
        st["win_job"] = None
        zoomed = root.state() == "zoomed"
        if root.state() not in ("normal", "zoomed"):
            return
        if zoomed:
            win = dict(cfg["window"] or {"w": 780, "h": 580, "x": None, "y": None}, zoomed=True)
        else:
            m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", root.geometry())
            if not m:
                return
            win = {"w": int(m[1]), "h": int(m[2]), "x": int(m[3]), "y": int(m[4]), "zoomed": False}
        win = sanitize_window(win)
        if win and win != cfg["window"]:
            cfg["window"] = win
            save()

    def on_configure(e):
        if e.widget is root:
            if st.get("win_job"):
                root.after_cancel(st["win_job"])
            st["win_job"] = root.after(600, remember_window)

    root.bind("<Configure>", on_configure)

    def on_close():
        remember_window()
        st["closing"] = True
        engine.release_all()
        output.pad.reset()
        if jc.get("thread"):
            jc["thread"].join(3)        # если joy.cpl как раз открывается — дождаться, чтобы потом закрыть
        close_joycpl(jc["pid"])
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    connect()
    refresh()
    update_vigem()
    tick()
    if cfg["joycpl"]:
        root.after(300, start_joycpl)
    root.mainloop()


if __name__ == "__main__":
    main()
