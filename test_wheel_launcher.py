import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from wheel_launcher import (Engine, NullInput, detect_input, key_from_event, Switcher, cycle_profile,
                             sanitize_config, active_rows, pressed_inputs, switch_inputs)


def mk():
    be = NullInput()
    return Engine(be), be


def test_axis_threshold_and_hysteresis():
    e, be = mk()
    b = [{"input": "axis0-", "key": "a", "threshold": 30}]
    e.update(b, [-0.2], [], []); assert be.log == []
    e.update(b, [-0.35], [], []); assert be.log == [("a", True)]
    e.update(b, [-0.25], [], []); assert be.log == [("a", True)]      # держится (гистерезис)
    e.update(b, [-0.15], [], []); assert be.log[-1] == ("a", False)
    e.update(b, [0.9], [], []); assert len(be.log) == 2               # другая сторона не жмёт


def test_button_hat_shared_key_and_release_all():
    e, be = mk()
    b = [{"input": "btn2", "key": "w"}, {"input": "hat0U", "key": "w"}]
    e.update(b, [], [0, 0, 1], [(0, 1)]); assert be.log == [("w", True)]   # одна клавиша = одно нажатие
    e.update(b, [], [0, 0, 0], [(0, 1)]); assert len(be.log) == 1          # D-pad ещё держит
    e.release_all(); assert be.log[-1] == ("w", False)


def test_detect_and_keys():
    assert detect_input([0, 0], [0, -0.9], [0], []) == "axis1-"
    assert detect_input([0], [0.1], [0, 1], []) == "btn1"
    assert detect_input([0], [0], [], [(-1, 0)]) == "hat0L"
    assert key_from_event(0x41, "Cyrillic_ef") == "a"


def test_old_config_migrates():
    cfg = sanitize_config({"current": "SnowRunner", "profiles": {"SnowRunner": [{"input": "btn1", "key": "w"}]}})
    assert cfg["profiles"]["SnowRunner"][0] == {"input": "btn1", "key": "w", "threshold": 30, "label": ""}
    assert cfg["switch"]["next"] == {"input": None, "key": None} and cfg["overlay"]["enabled"] is True
    assert sanitize_config({"current": "нет", "profiles": {}})["current"] == "Forza Horizon"


def test_switch_by_wheel_and_key_edges():
    cfg = sanitize_config(None)
    cfg["profiles"]["Третий"] = []
    cfg["switch"]["next"] = {"input": "btn7", "key": None}
    cfg["switch"]["prev"] = {"input": None, "key": "f9"}
    s, keys = Switcher(), set()
    kd = lambda k: k in keys
    assert s.poll(cfg, [], [0] * 8, [], kd) == 0
    assert s.poll(cfg, [], [0] * 7 + [1], [], kd) == 1
    assert s.poll(cfg, [], [0] * 7 + [1], [], kd) == 0          # держим — второй раз не листает
    keys.add("f9")
    assert s.poll(cfg, [], [0] * 8, [], kd) == -1
    assert cycle_profile(cfg, 1) == "SnowRunner" and cycle_profile(cfg, -1) == "Третий"
    assert switch_inputs(cfg) == {"btn7"}


def test_highlight_rows_and_pressed():
    b = [{"input": "btn0", "key": "a", "threshold": 30}, {"input": "axis0+", "key": "d", "threshold": 30},
         {"input": "hat0U", "key": "w", "threshold": 30}]
    assert active_rows(b, [0.5], [1], [(0, 0)]) == {0, 1}
    assert active_rows(b, [0.1], [0], [(0, 1)]) == {2}
    assert pressed_inputs([0, 1], [(1, 0)]) == ["btn1", "hat0R"]


def test_joycpl_option_default_on():
    assert sanitize_config(None)["joycpl"] is True
    assert sanitize_config({"joycpl": False})["joycpl"] is False


def test_profile_export_import(tmp_path):
    from wheel_launcher import export_profile, import_profile, unique_name
    import pytest
    f = str(tmp_path / "p.json")
    export_profile(f, "Гонка", [{"input": "btn3", "key": "w", "threshold": 30, "label": "Газ"}])
    n, bl, pad = import_profile(f)
    assert (n, bl) == ("Гонка", [{"input": "btn3", "key": "w", "threshold": 30, "label": "Газ"}])
    assert pad["enabled"] is False
    assert unique_name("Гонка", {"Гонка": [], "Гонка (2)": []}) == "Гонка (3)"
    (tmp_path / "bad.json").write_text('{"a": 1}')
    with pytest.raises(ValueError):
        import_profile(str(tmp_path / "bad.json"))


def test_numpad_keys_distinct_from_top_row():
    from wheel_launcher import KEYS, key_label, key_from_event, KEY_BY_LABEL
    assert KEYS["num5"] == (0x4C, False) and KEYS["5"] == (0x06, False)     # разные scan-коды
    assert key_label("num5") == "Num 5" and KEY_BY_LABEL["Num 5"] == "num5"
    assert key_from_event(0x65, "KP_5") == "num5" and key_from_event(0x35, "5") == "5"
    assert key_from_event(0x0D, "KP_Enter") == "num_enter"


def test_steer_and_pedals():
    from wheel_launcher import steer_value, pedal_value, pad_values, pad_busy, sanitize_pad
    assert steer_value(0.02, 3, 100, False) == 0.0                    # мёртвая зона
    assert steer_value(1.0, 3, 100, False) == 1.0 and steer_value(-1.0, 3, 100, False) == -1.0
    assert abs(steer_value(0.5, 0, 50, False) - 1.0) < 1e-9           # 50 % хода руля = полный поворот
    assert steer_value(0.5, 0, 100, True) == -0.5                     # инверсия
    assert steer_value(0.3, 3, 100, False) < steer_value(0.31, 3, 100, False)   # плавно, возврат руля = возврат стика
    axes = [0.4, -0.8]
    assert pedal_value("axis1-", axes, [], []) > 0.7 and pedal_value("axis1+", axes, [], []) == 0.0
    assert pedal_value("btn0", [], [1], []) == 1.0 and pedal_value(None, [], [], []) == 0.0
    pd = sanitize_pad({"enabled": True, "axis": 0, "throttle": "axis1-", "brake": "axis1+"})
    st_, gas, brk = pad_values(pd, axes, [], [])
    assert 0.3 < st_ < 0.5 and gas > 0.7 and brk == 0.0
    assert pad_busy(pd) == {"axis0+", "axis0-", "axis1-", "axis1+"} and pad_busy(sanitize_pad(None)) == set()


def test_pad_output_routes_buttons_and_axes(monkeypatch):
    import sys, types
    from wheel_launcher import Output, Engine
    calls = []

    class Pad:
        def reset(self): calls.append("reset")
        def update(self): calls.append("upd")
        def press_button(self, button): calls.append(("press", button))
        def release_button(self, button): calls.append(("rel", button))
        def left_joystick_float(self, x_value_float, y_value_float): calls.append(("ls", x_value_float))
        def right_joystick_float(self, x_value_float, y_value_float): pass
        def right_trigger_float(self, value_float): calls.append(("rt", value_float))
        def left_trigger_float(self, value_float): calls.append(("lt", value_float))
    vg = types.SimpleNamespace(VX360Gamepad=Pad, XUSB_BUTTON=types.SimpleNamespace(XUSB_GAMEPAD_A="A"))
    monkeypatch.setitem(sys.modules, "vgamepad", vg)
    from wheel_launcher import NullInput
    out = Output(kb=NullInput())
    e = Engine(out)
    e.update([{"input": "btn0", "key": "pad_a"}, {"input": "btn1", "key": "w"}], [], [1, 1], [])
    assert ("press", "A") in calls and out.kb.log == [("w", True)]
    out.pad.axes(0.5, 0.25, 0.0); n = len(calls); out.pad.axes(0.5, 0.25, 0.0)
    assert ("ls", 0.5) in calls and ("rt", 0.25) in calls and len(calls) == n    # без изменений — не шлёт
    e.release_all(); assert ("rel", "A") in calls


def test_pad_analog_buttons(monkeypatch):
    import sys, types
    from wheel_launcher import Output, NullInput, PAD_BUTTONS
    calls = []

    class Pad:
        def reset(self): pass
        def update(self): pass
        def press_button(self, button): pass
        def release_button(self, button): pass
        def left_joystick_float(self, x_value_float, y_value_float): calls.append(("ls", x_value_float, y_value_float))
        def right_joystick_float(self, x_value_float, y_value_float): calls.append(("rs", x_value_float, y_value_float))
        def right_trigger_float(self, value_float): calls.append(("rt", value_float))
        def left_trigger_float(self, value_float): calls.append(("lt", value_float))
    monkeypatch.setitem(sys.modules, "vgamepad", types.SimpleNamespace(VX360Gamepad=Pad, XUSB_BUTTON=None))
    out = Output(kb=NullInput())
    out.send("pad_rt", True); assert ("rt", 1.0) in calls
    out.send("pad_lsu", True); assert ("ls", 0.0, 1.0) in calls
    out.pad.axes(0.5, 0.0, 0.0); assert ("ls", 0.5, 1.0) in calls and ("rt", 1.0) in calls   # руль + кнопка вместе
    out.send("pad_rt", False); out.send("pad_lsu", False); assert ("rt", 0.0) in calls and ("ls", 0.5, 0.0) in calls
    assert "pad_guide" in PAD_BUTTONS


def test_pad_config_per_profile():
    from wheel_launcher import sanitize_config
    c = sanitize_config({"profiles": {"A": [], "B": []}, "pads": {"A": {"enabled": True, "axis": 2}, "Z": {}}})
    assert c["pads"]["A"]["enabled"] is True and c["pads"]["A"]["axis"] == 2
    assert c["pads"]["B"]["enabled"] is False and "Z" not in c["pads"]


def test_vigem_status_text():
    from wheel_launcher import vigem_status, vigem_installed
    assert vigem_status(True, True)[1] is True and "установлен" in vigem_status(True, False)[0]
    txt, ok = vigem_status(False, True)
    assert ok is False and "НЕ установлен" in txt and "работать не будет" in txt
    assert "работать не будет" not in vigem_status(False, False)[0]
    assert vigem_status(None, False)[1] is True
    assert vigem_installed() in (True, False, None)


def test_window_size_saved_and_clamped():
    from wheel_launcher import sanitize_window, window_geometry, sanitize_config
    assert sanitize_window(None) is None and sanitize_window({"w": 100, "h": 100}) is None
    w = sanitize_window({"w": 900, "h": 650, "x": 40, "y": 30, "zoomed": True})
    assert w == {"w": 900, "h": 650, "x": 40, "y": 30, "zoomed": True}
    assert window_geometry(w, 1920, 1080) == "900x650+40+30"
    assert window_geometry(dict(w, x=5000), 1920, 1080) == "900x650"        # окно за экраном — без положения
    assert window_geometry(dict(w, w=4000, h=3000), 1920, 1080) == "1920x1080+40+30"
    assert sanitize_config({"window": {"w": 900, "h": 650}})["window"]["x"] is None
    assert sanitize_config(None)["window"] is None


def test_copy_settings_between_profiles():
    from wheel_launcher import copy_settings, sanitize_config
    cfg = sanitize_config({"profiles": {"Движение": [{"input": "btn1", "key": "w"}, {"input": "btn2", "key": "s"}],
                                         "Обзор": [{"input": "btn1", "key": "x"}, {"input": "btn5", "key": "q"}]},
                           "pads": {"Движение": {"enabled": True, "axis": 2, "range": 80, "throttle": "axis1-", "brake": "axis1+"}}})
    assert copy_settings(cfg, "Движение", [0], True, False, ["Обзор", "Движение"]) == 1   # себя пропускаем
    assert cfg["profiles"]["Обзор"] == [{"input": "btn1", "key": "w", "threshold": 30, "label": ""},
                                        {"input": "btn5", "key": "q", "threshold": 30, "label": ""}]   # заменена, не продублирована
    p = cfg["pads"]["Обзор"]
    assert p["axis"] == 2 and p["range"] == 80 and p["enabled"] and p["throttle"] is None   # педали не отмечены
    copy_settings(cfg, "Движение", [1], False, True, ["Обзор"])
    assert cfg["profiles"]["Обзор"][-1]["input"] == "btn2" and cfg["pads"]["Обзор"]["brake"] == "axis1+"
    cfg["profiles"]["Обзор"][-1]["key"] = "z"
    assert cfg["profiles"]["Движение"][1]["key"] == "s"          # копия, а не общая ссылка


def test_pad_rows_shown_in_list():
    from wheel_launcher import pad_rows, sanitize_pad
    assert pad_rows(sanitize_pad({})) == []                      # геймпад выключен — строк нет
    r = pad_rows(sanitize_pad({"enabled": True, "axis": 0, "throttle": "axis1-", "brake": "btn3"}))
    assert [x[0] for x in r] == ["steer", "throttle", "brake"] and r[0][1] == "Ось X"
