# DuckWave

> Smart real-time audio ducking for Windows

DuckWave automatically lowers the volume of selected applications when voice or audio activity is detected, then smoothly restores the volume when the activity stops.

It can detect audio from your **microphone** and/or **specific applications**, such as Discord, games, browsers, and other audio sources.

**Windows only.**

## Download

The easiest way to use DuckWave is to download the latest installer from the **Releases** page.

Download `DuckWaveSetup.exe`, run the installer, and follow the instructions.

No Python installation is required when using the installer.

## Features

* Microphone voice detection
* Per-application audio detection
* Automatic ducking
* Custom ducking percentage
* Adjustable sensitivity
* Multiple detection sources
* Smooth volume transitions
* Windows system tray integration
* Portuguese and English interface

## How It Works

DuckWave monitors the audio sources you select.

When the detected audio reaches the configured threshold, DuckWave lowers the volume of the selected applications.

When the audio activity stops, the volume is gradually restored.

### Detection Sources

**Microphone**

Detects voice activity from your selected microphone.

**Applications**

Monitors the audio level of selected Windows applications. For example, you can monitor Discord and automatically lower your music when someone speaks.

Both detection sources can be enabled independently or used together.

## Ducking Modes

**Automatic**

Adjusts the amount of volume reduction dynamically based on the detected audio level.

**Custom**

Lets you choose a specific volume reduction percentage using a slider.

## Running From Source

If you want to run or modify DuckWave from source, install **Python 3.10, 3.11, or 3.12**.

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

## Building the Executable

To create a standalone executable:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name DuckWave main.py
```

The executable will be created in:

```text
dist\DuckWave.exe
```

## Building the Installer

DuckWave uses **Inno Setup** to create the Windows installer.

1. Build `DuckWave.exe` using PyInstaller.
2. Install Inno Setup.
3. Open `installer\setup.iss`.
4. Compile the installer.

The final installer will be generated in:

```text
installer\output\DuckWaveSetup.exe
```

## Open Source

DuckWave is a small open-source project.

The source code is publicly available, and you're free to download it, modify it, experiment with it, or use it as a starting point for your own projects.

Feel free to make changes and improvements as you see fit.

## Status

DuckWave is currently under development.

## License

See the `LICENSE` file for more information.
