# DuckWave

> Smart real-time audio ducking for Windows

DuckWave is a small Windows application that automatically lowers the volume of selected applications when voice or audio activity is detected, then smoothly restores the volume when the activity stops.

It can detect audio from your **microphone** and/or **specific applications**, such as Discord, games, browsers, and other audio sources.

**Windows only.**

## Download

The easiest way to use DuckWave is to download the latest `.exe` from the **Releases** page.

Download `DuckWave.exe` and run it. **No Python installation is required.**

## Features

* Microphone voice detection
* Per-application audio detection
* Automatic volume ducking
* Custom ducking percentage
* Adjustable sensitivity
* Multiple detection sources
* Smooth volume transitions
* Windows system tray integration
* Portuguese and English interface

## How It Works

DuckWave monitors the audio sources you select.

When the detected audio reaches the configured threshold, DuckWave lowers the volume of the applications you selected.

When the audio activity stops, the volume is gradually restored.

### Detection Sources

**Microphone**

Detects voice activity from your selected microphone.

**Applications**

Monitors the audio level of selected Windows applications.

For example, you can monitor Discord and automatically lower your music when someone speaks.

Both detection sources can be enabled independently or used together.

### Ducking Modes

**Automatic**

Adjusts the amount of volume reduction dynamically based on the detected audio level.

**Custom**

Lets you choose a specific volume reduction percentage using a slider.

## Running From Source

If you want to run DuckWave from source or modify the project, install **Python 3.10, 3.11, or 3.12**.

Clone the repository and install the dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Run DuckWave with:

```bash
python main.py
```

## Open Source

DuckWave is a small open-source project.

The source code is publicly available, and you're free to download it, modify it, experiment with it, or use it as a starting point for your own projects.

The `.exe` available in **Releases** is provided as a convenient way to use DuckWave without installing Python or setting up the project yourself.

If you prefer, you can also build the application yourself directly from the source code.

## Status

DuckWave is currently under development.

## License

See the `LICENSE` file for more information.
