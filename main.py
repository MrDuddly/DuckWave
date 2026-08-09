# -*- coding: utf-8 -*-
"""
DuckWave - abaixa o volume de um app (ex: Spotify) quando alguem fala.
DuckWave - ducks (lowers) an app's volume (e.g. Spotify) when someone talks.

Fontes de voz / Voice sources:
- Microfone fisico / Physical microphone.
- Nivel de audio de outro app (ex: um app de chamada, um jogo) - o Windows expoe
  o "medidor de pico" de cada app individualmente. Quando esse app passa de um
  certo nivel, considera-se que tem alguem falando nele.
  / Audio level of another app (e.g. a call app, a game) - Windows exposes a
  "peak meter" per app. When that app goes above a level, someone is assumed
  to be talking there.

So funciona no Windows. / Windows only.
"""

import sys
import os
import json
import time
import threading
import ctypes

import numpy as np
import sounddevice as sd
import comtypes
from comtypes import GUID, COMMETHOD, HRESULT, IUnknown
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

import psutil
import win32gui
import win32process

import pystray
from PIL import Image, ImageDraw

APP_NAME = "DuckWave"

# ---------------------------------------------------------------------------
# Interface COM para medir o pico de audio de uma sessao (app) especifica
# ---------------------------------------------------------------------------

class IAudioMeterInformation(IUnknown):
    _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetPeakValue",
                  (["out"], ctypes.POINTER(ctypes.c_float), "pfPeak")),
    ]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Textos (PT / EN)
# ---------------------------------------------------------------------------

STRINGS = {
    "pt": {
        "menu_active": "Ativo",
        "menu_targets": "App(s) para abaixar",
        "menu_mic": "Microfone",
        "mic_use": "Usar microfone",
        "mic_refresh": "Atualizar lista",
        "mic_default": "Padrão do sistema",
        "menu_mic_sensitivity": "Sensibilidade do microfone",
        "sens_low": "Baixa (só voz alta)",
        "sens_medium": "Média",
        "sens_high": "Alta (detecta sussurro)",
        "menu_app_trigger": "Detecção por app externo",
        "apptrig_enabled": "Ativado",
        "apptrig_apps": "Apps monitorados",
        "apptrig_sensitivity": "Sensibilidade",
        "apptrig_low": "Baixa (10%)",
        "apptrig_medium": "Média (20%)",
        "apptrig_high": "Alta (35%)",
        "auto": "Automático",
        "custom_open": "Personalizado (abrir controle deslizante)...",
        "menu_duck_amount": "Quanto abaixar",
        "menu_language": "Idioma / Language",
        "no_apps": "(nenhum app encontrado)",
        "menu_quit": "Sair",
        "slider_title_duck": "DuckWave - nível personalizado",
        "slider_label_duck": "Abaixar o app para {pct}% do volume original",
        "slider_title_trigger": "DuckWave - sensibilidade personalizada",
        "slider_label_trigger": "Detectar quando o app passar de {pct}% de volume",
    },
    "en": {
        "menu_active": "Active",
        "menu_targets": "App(s) to duck",
        "menu_mic": "Microphone",
        "mic_use": "Use microphone",
        "mic_refresh": "Refresh list",
        "mic_default": "System default",
        "menu_mic_sensitivity": "Microphone sensitivity",
        "sens_low": "Low (loud voice only)",
        "sens_medium": "Medium",
        "sens_high": "High (detects whispers)",
        "menu_app_trigger": "External app detection",
        "apptrig_enabled": "Enabled",
        "apptrig_apps": "Monitored apps",
        "apptrig_sensitivity": "Sensitivity",
        "apptrig_low": "Low (10%)",
        "apptrig_medium": "Medium (20%)",
        "apptrig_high": "High (35%)",
        "auto": "Automatic",
        "custom_open": "Custom (open slider)...",
        "menu_duck_amount": "How much to duck",
        "menu_language": "Idioma / Language",
        "no_apps": "(no app found)",
        "menu_quit": "Exit",
        "slider_title_duck": "DuckWave - custom level",
        "slider_label_duck": "Duck the app to {pct}% of its original volume",
        "slider_title_trigger": "DuckWave - custom sensitivity",
        "slider_label_trigger": "Detect when the app goes above {pct}% volume",
    },
}


def tr(config, key):
    lang = config.get("language", "pt")
    return STRINGS.get(lang, STRINGS["pt"]).get(key, key)


# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_base_dir(), "config.json")

DEFAULT_CONFIG = {
    "language": "pt",  # "pt" ou "en"

    "target_apps": ["Spotify.exe"],
    "threshold_db": -35.0,

    "duck_mode": "custom",       # "custom" ou "auto"
    "ducked_volume": 0.15,       # usado no modo custom
    "auto_min_volume": 0.10,     # modo auto: volume quando a voz esta bem baixa
    "auto_max_volume": 0.55,     # modo auto: volume quando a voz esta bem alta

    "fade_ms": 250,
    "hangover_ms": 600,

    "mic_enabled": True,
    "mic_device_name": None,

    "app_trigger_enabled": True,
    "app_trigger_processes": [],
    "app_trigger_mode": "custom",     # "custom" ou "auto"
    "app_trigger_threshold": 0.15,    # 0..1, usado no modo custom
    "app_trigger_auto_margin": 0.10,  # modo auto: quanto acima do nivel de base conta como fala

    "enabled": True,
}

SENSITIVITY_LEVELS = [
    ("sens_low", -25.0),
    ("sens_medium", -35.0),
    ("sens_high", -45.0),
]

DUCK_LEVEL_PRESETS = [10, 25, 50]           # porcentagens fixas do modo custom (abaixar)
APP_TRIGGER_PRESETS = [
    ("apptrig_low", 0.10),
    ("apptrig_medium", 0.20),
    ("apptrig_high", 0.35),
]

IGNORED_PROCESSES = {
    "python.exe", "pythonw.exe", "main.exe", "duckwave.exe",
    "explorer.exe", "svchost.exe", "audiodg.exe", "dwm.exe",
    "textinputhost.exe", "searchhost.exe", "shellexperiencehost.exe",
    "applicationframehost.exe", "systemsettings.exe",
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
        except Exception:
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Config save error:", e)


# ---------------------------------------------------------------------------
# Helpers: listar dispositivos de audio e apps candidatos
# ---------------------------------------------------------------------------

def list_input_devices():
    names = []
    try:
        for d in sd.query_devices():
            if d.get("max_input_channels", 0) > 0 and d["name"] not in names:
                names.append(d["name"])
    except Exception as e:
        print("Error listing microphones:", e)
    return names


def resolve_input_device_index(name):
    if not name:
        return None
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["name"] == name and d.get("max_input_channels", 0) > 0:
                return i
    except Exception:
        pass
    return None


def list_windowed_process_names():
    pids = set()

    def _enum_handler(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                pids.add(pid)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_enum_handler, None)
    except Exception as e:
        print("Error enumerating windows:", e)

    names = set()
    for pid in pids:
        try:
            p = psutil.Process(pid)
            n = p.name()
            if n.lower() not in IGNORED_PROCESSES:
                names.add(n)
        except Exception:
            pass
    return names


def list_audio_session_process_names():
    names = set()
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process:
                n = s.Process.name()
                if n.lower() not in IGNORED_PROCESSES:
                    names.add(n)
    except Exception as e:
        print("Error listing audio sessions:", e)
    return names


def list_candidate_apps():
    with_audio = list_audio_session_process_names()
    windowed = list_windowed_process_names()
    all_names = with_audio | windowed
    labeled = []
    for n in sorted(all_names, key=str.lower):
        label = f"🔊 {n}" if n in with_audio else n
        labeled.append((label, n))
    return labeled


# ---------------------------------------------------------------------------
# Nucleo: deteccao de voz (mic + apps) + controle de volume por app
# ---------------------------------------------------------------------------

class VoiceDucker:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.speaking = False
        self.last_voice_time = 0.0
        self.last_loudness = 0.0  # 0..1, usado no modo automatico de "quanto abaixar"
        self._current_scale = 1.0
        self._original_volumes = {}
        self._app_baseline = {}  # nome_processo -> nivel de base (EMA) p/ modo auto do gatilho

        self._mic_stream = None
        self._app_meter_thread = None
        self._control_thread = None
        self._stop_event = threading.Event()

    def note_voice(self, loudness=None):
        self.last_voice_time = time.time()
        self.speaking = True
        if loudness is not None:
            self.last_loudness = clamp(loudness, 0.0, 1.0)

    def _sessions_for(self, process_names):
        targets = {p.lower() for p in process_names}
        matches = []
        try:
            for s in AudioUtilities.GetAllSessions():
                if s.Process and s.Process.name().lower() in targets:
                    matches.append(s)
        except Exception as e:
            print("Error fetching sessions:", e)
        return matches

    def _apply_scale(self, scale):
        try:
            for s in self._sessions_for(self.config["target_apps"]):
                name = s.Process.name()
                volume_ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                base = self._original_volumes.get(name)
                if base is None:
                    base = volume_ctl.GetMasterVolume()
                    self._original_volumes[name] = base
                new_vol = clamp(base * scale, 0.0, 1.0)
                volume_ctl.SetMasterVolume(new_vol, None)
        except Exception as e:
            print("Error applying volume:", e)

    # -- Fonte 1: microfone fisico -------------------------------------------
    def _mic_callback(self, indata, frames, time_info, status):
        rms = np.sqrt(np.mean(np.square(indata.astype(np.float64))) + 1e-12)
        db = 20 * np.log10(rms + 1e-9)
        threshold = self.config["threshold_db"]
        if db > threshold:
            loudness = clamp((db - threshold) / 40.0, 0.0, 1.0)
            self.note_voice(loudness=loudness)

    def _start_mic(self):
        if not self.config["mic_enabled"]:
            return
        device_index = resolve_input_device_index(self.config["mic_device_name"])
        try:
            self._mic_stream = sd.InputStream(
                channels=1, samplerate=16000, blocksize=1024,
                device=device_index, callback=self._mic_callback,
            )
            self._mic_stream.start()
        except Exception as e:
            print("Could not open selected microphone, falling back to default:", e)
            self._mic_stream = sd.InputStream(
                channels=1, samplerate=16000, blocksize=1024,
                callback=self._mic_callback,
            )
            self._mic_stream.start()

    # -- Fonte 2: volume de outro app (ex: chamada de voz, jogo) -------------
    def _app_meter_loop(self):
        comtypes.CoInitialize()
        try:
            while not self._stop_event.is_set():
                if self.config["app_trigger_enabled"] and self.config["app_trigger_processes"]:
                    mode = self.config["app_trigger_mode"]
                    for s in self._sessions_for(self.config["app_trigger_processes"]):
                        name = s.Process.name()
                        try:
                            meter = s._ctl.QueryInterface(IAudioMeterInformation)
                            peak = meter.GetPeakValue()
                        except Exception:
                            continue

                        if mode == "auto":
                            baseline = self._app_baseline.get(name, peak)
                            # so atualiza a base quando NAO parece um pico de fala,
                            # pra base nao "perseguir" a propria fala
                            if peak < baseline + 0.15:
                                alpha = 0.02
                                baseline = baseline * (1 - alpha) + peak * alpha
                            self._app_baseline[name] = baseline
                            threshold = baseline + self.config["app_trigger_auto_margin"]
                        else:
                            threshold = self.config["app_trigger_threshold"]

                        if peak > threshold:
                            loudness = clamp((peak - threshold) / max(1e-6, (1.0 - threshold)), 0.0, 1.0)
                            self.note_voice(loudness=loudness)
                time.sleep(0.08)
        finally:
            comtypes.CoUninitialize()

    # -- Loop que aplica o fade suave de volume -------------------------------
    def _control_loop(self):
        comtypes.CoInitialize()
        fade_steps = 12
        try:
            while not self._stop_event.is_set():
                now = time.time()
                if self.speaking and (now - self.last_voice_time) * 1000 > self.config["hangover_ms"]:
                    self.speaking = False

                want_duck = self.speaking and self.config["enabled"]

                if want_duck:
                    if self.config["duck_mode"] == "auto":
                        lo = self.config["auto_min_volume"]
                        hi = self.config["auto_max_volume"]
                        target_scale = lo + (hi - lo) * self.last_loudness
                    else:
                        target_scale = self.config["ducked_volume"]
                else:
                    target_scale = 1.0

                if abs(target_scale - self._current_scale) > 0.005:
                    step = (target_scale - self._current_scale) / fade_steps
                    sleep_per_step = max(0.005, (self.config["fade_ms"] / 1000) / fade_steps)
                    for _ in range(fade_steps):
                        if self._stop_event.is_set():
                            break
                        self._current_scale += step
                        self._apply_scale(self._current_scale)
                        time.sleep(sleep_per_step)
                    self._current_scale = target_scale
                    self._apply_scale(self._current_scale)

                    if self._current_scale >= 0.999:
                        self._original_volumes.clear()

                time.sleep(0.05)
        finally:
            comtypes.CoUninitialize()

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._start_mic()
        self._app_meter_thread = threading.Thread(target=self._app_meter_loop, daemon=True)
        self._app_meter_thread.start()
        self._control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._control_thread.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._stop_event.set()
        if self._control_thread:
            self._control_thread.join(timeout=2)
        if self._app_meter_thread:
            self._app_meter_thread.join(timeout=2)
        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None
        self._apply_scale(1.0)
        self._original_volumes.clear()
        self._current_scale = 1.0

    def restart(self):
        self.stop()
        self.start()


# ---------------------------------------------------------------------------
# Janela com controle deslizante (slider) - reutilizavel
# ---------------------------------------------------------------------------

_slider_open = threading.Event()


def open_custom_slider(config, value_key, mode_key, title, label_template, min_pct=5, max_pct=90):
    if _slider_open.is_set():
        return
    _slider_open.set()

    def run():
        import tkinter as tk
        try:
            root = tk.Tk()
            root.title(title)
            root.attributes("-topmost", True)
            root.geometry("380x120")
            root.resizable(False, False)

            initial_pct = int(round(config[value_key] * 100))
            label = tk.Label(root, text=label_template.format(pct=initial_pct))
            label.pack(pady=(14, 0))

            def on_move(value):
                pct = int(float(value))
                label.config(text=label_template.format(pct=pct))
                config[mode_key] = "custom"
                config[value_key] = pct / 100.0
                save_config(config)

            scale = tk.Scale(
                root, from_=min_pct, to=max_pct, orient="horizontal", length=340,
                showvalue=False, command=on_move,
            )
            scale.set(initial_pct)
            scale.pack(pady=10)

            def on_close():
                _slider_open.clear()
                root.destroy()

            root.protocol("WM_DELETE_WINDOW", on_close)
            root.mainloop()
        finally:
            _slider_open.clear()

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# Icone da bandeja (system tray) e menu
# ---------------------------------------------------------------------------

def make_icon_image(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=color)
    return img


def build_app():
    config = load_config()
    ducker = VoiceDucker(config)
    ducker.start()

    def on_toggle_enabled(icon, item):
        config["enabled"] = not config["enabled"]
        save_config(config)

    def is_enabled(item):
        return config["enabled"]

    # -- Apps para abaixar --
    def make_target_toggle(app_name):
        def handler(icon, item):
            if app_name in config["target_apps"]:
                config["target_apps"].remove(app_name)
            else:
                config["target_apps"].append(app_name)
            save_config(config)
        return handler

    def is_target_checked(app_name):
        def checker(item):
            return app_name in config["target_apps"]
        return checker

    def build_targets_submenu():
        candidates = list_candidate_apps()
        known = {n for _, n in candidates}
        for a in config["target_apps"]:
            if a not in known:
                candidates.append((a, a))
        if not candidates:
            return pystray.Menu(pystray.MenuItem(tr(config, "no_apps"), None, enabled=False))
        items = [
            pystray.MenuItem(label, make_target_toggle(name), checked=is_target_checked(name))
            for label, name in candidates
        ]
        return pystray.Menu(*items)

    # -- Microfone --
    def make_mic_handler(device_name):
        def handler(icon, item):
            config["mic_device_name"] = device_name
            save_config(config)
            ducker.restart()
        return handler

    def is_mic_checked(device_name):
        def checker(item):
            return config["mic_device_name"] == device_name
        return checker

    def on_toggle_mic_enabled(icon, item):
        config["mic_enabled"] = not config["mic_enabled"]
        save_config(config)
        ducker.restart()

    def is_mic_enabled_checked(item):
        return config["mic_enabled"]

    def on_refresh_mics(icon, item):
        icon.update_menu()

    def build_mic_submenu():
        devices = list_input_devices()
        items = [
            pystray.MenuItem(tr(config, "mic_use"), on_toggle_mic_enabled, checked=is_mic_enabled_checked),
            pystray.MenuItem(tr(config, "mic_refresh"), on_refresh_mics),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr(config, "mic_default"), make_mic_handler(None), checked=is_mic_checked(None), radio=True),
        ]
        for d in devices:
            items.append(pystray.MenuItem(d, make_mic_handler(d), checked=is_mic_checked(d), radio=True))
        return pystray.Menu(*items)

    # -- Sensibilidade do microfone --
    def make_sensitivity_handler(value_db):
        def handler(icon, item):
            config["threshold_db"] = value_db
            save_config(config)
        return handler

    def is_sensitivity_checked(value_db):
        def checker(item):
            return config["threshold_db"] == value_db
        return checker

    # -- Detecção por app externo --
    def on_toggle_app_trigger(icon, item):
        config["app_trigger_enabled"] = not config["app_trigger_enabled"]
        save_config(config)

    def is_app_trigger_enabled(item):
        return config["app_trigger_enabled"]

    def make_trigger_app_toggle(app_name):
        def handler(icon, item):
            if app_name in config["app_trigger_processes"]:
                config["app_trigger_processes"].remove(app_name)
            else:
                config["app_trigger_processes"].append(app_name)
            save_config(config)
        return handler

    def is_trigger_app_checked(app_name):
        def checker(item):
            return app_name in config["app_trigger_processes"]
        return checker

    def build_trigger_apps_submenu():
        candidates = list_candidate_apps()
        known = {n for _, n in candidates}
        for a in config["app_trigger_processes"]:
            if a not in known:
                candidates.append((a, a))
        if not candidates:
            return pystray.Menu(pystray.MenuItem(tr(config, "no_apps"), None, enabled=False))
        items = [
            pystray.MenuItem(label, make_trigger_app_toggle(name), checked=is_trigger_app_checked(name))
            for label, name in candidates
        ]
        return pystray.Menu(*items)

    # -- Sensibilidade do app externo: Automático / presets / slider --
    def on_set_app_trigger_auto(icon, item):
        config["app_trigger_mode"] = "auto"
        save_config(config)

    def is_app_trigger_auto_checked(item):
        return config["app_trigger_mode"] == "auto"

    def make_app_trigger_preset_handler(value):
        def handler(icon, item):
            config["app_trigger_mode"] = "custom"
            config["app_trigger_threshold"] = value
            save_config(config)
        return handler

    def is_app_trigger_preset_checked(value):
        def checker(item):
            return config["app_trigger_mode"] == "custom" and abs(config["app_trigger_threshold"] - value) < 0.001
        return checker

    def on_open_app_trigger_slider(icon, item):
        open_custom_slider(
            config, "app_trigger_threshold", "app_trigger_mode",
            title=tr(config, "slider_title_trigger"),
            label_template=tr(config, "slider_label_trigger"),
            min_pct=5, max_pct=80,
        )

    def build_app_trigger_sensitivity_submenu():
        preset_items = [
            pystray.MenuItem(tr(config, key), make_app_trigger_preset_handler(val),
                              checked=is_app_trigger_preset_checked(val), radio=True)
            for key, val in APP_TRIGGER_PRESETS
        ]
        return pystray.Menu(
            pystray.MenuItem(tr(config, "auto"), on_set_app_trigger_auto, checked=is_app_trigger_auto_checked, radio=True),
            pystray.Menu.SEPARATOR,
            *preset_items,
            pystray.MenuItem(tr(config, "custom_open"), on_open_app_trigger_slider),
        )

    def build_app_trigger_submenu():
        return pystray.Menu(
            pystray.MenuItem(tr(config, "apptrig_enabled"), on_toggle_app_trigger, checked=is_app_trigger_enabled),
            pystray.MenuItem(tr(config, "apptrig_apps"), pystray.Menu(build_trigger_apps_submenu)),
            pystray.MenuItem(tr(config, "apptrig_sensitivity"), pystray.Menu(build_app_trigger_sensitivity_submenu)),
        )

    # -- Quanto abaixar: Automático / presets / slider --
    def on_set_duck_auto(icon, item):
        config["duck_mode"] = "auto"
        save_config(config)

    def is_duck_auto_checked(item):
        return config["duck_mode"] == "auto"

    def make_duck_preset_handler(pct):
        def handler(icon, item):
            config["duck_mode"] = "custom"
            config["ducked_volume"] = pct / 100.0
            save_config(config)
        return handler

    def is_duck_preset_checked(pct):
        def checker(item):
            return config["duck_mode"] == "custom" and abs(config["ducked_volume"] - pct / 100.0) < 0.001
        return checker

    def on_open_duck_slider(icon, item):
        open_custom_slider(
            config, "ducked_volume", "duck_mode",
            title=tr(config, "slider_title_duck"),
            label_template=tr(config, "slider_label_duck"),
            min_pct=5, max_pct=90,
        )

    def build_duck_amount_submenu():
        preset_items = [
            pystray.MenuItem(f"{pct}%", make_duck_preset_handler(pct), checked=is_duck_preset_checked(pct), radio=True)
            for pct in DUCK_LEVEL_PRESETS
        ]
        return pystray.Menu(
            pystray.MenuItem(tr(config, "auto"), on_set_duck_auto, checked=is_duck_auto_checked, radio=True),
            pystray.Menu.SEPARATOR,
            *preset_items,
            pystray.MenuItem(tr(config, "custom_open"), on_open_duck_slider),
        )

    # -- Idioma / Language --
    def make_language_handler(lang_code):
        def handler(icon, item):
            config["language"] = lang_code
            save_config(config)
            icon.update_menu()
        return handler

    def is_language_checked(lang_code):
        def checker(item):
            return config.get("language", "pt") == lang_code
        return checker

    def build_language_submenu():
        return pystray.Menu(
            pystray.MenuItem("Português", make_language_handler("pt"), checked=is_language_checked("pt"), radio=True),
            pystray.MenuItem("English", make_language_handler("en"), checked=is_language_checked("en"), radio=True),
        )

    def on_quit(icon, item):
        ducker.stop()
        icon.stop()

    def build_menu():
        sensitivity_items = [
            pystray.MenuItem(tr(config, key), make_sensitivity_handler(val), checked=is_sensitivity_checked(val), radio=True)
            for key, val in SENSITIVITY_LEVELS
        ]
        return pystray.Menu(
            pystray.MenuItem(tr(config, "menu_active"), on_toggle_enabled, checked=is_enabled),
            pystray.MenuItem(tr(config, "menu_targets"), pystray.Menu(build_targets_submenu)),
            pystray.MenuItem(tr(config, "menu_mic"), pystray.Menu(build_mic_submenu)),
            pystray.MenuItem(tr(config, "menu_mic_sensitivity"), pystray.Menu(*sensitivity_items)),
            pystray.MenuItem(tr(config, "menu_app_trigger"), pystray.Menu(build_app_trigger_submenu)),
            pystray.MenuItem(tr(config, "menu_duck_amount"), pystray.Menu(build_duck_amount_submenu)),
            pystray.MenuItem(tr(config, "menu_language"), pystray.Menu(build_language_submenu)),
            pystray.MenuItem(tr(config, "menu_quit"), on_quit),
        )

    icon = pystray.Icon(
        "duckwave",
        icon=make_icon_image((30, 200, 90, 255)),
        title=APP_NAME,
        menu=pystray.Menu(build_menu),
    )
    return icon, ducker


def main():
    icon, ducker = build_app()
    try:
        icon.run()
    finally:
        ducker.stop()


if __name__ == "__main__":
    main()
