# Kimi_V Web UI Control Panel

This is a modern Web UI for managing Kimi_V automation tasks, built with [NiceGUI](https://nicegui.io/).

## Features

- **Dashboard**: View current Domain and Aesthetics configurations.
- **Cookie Manager**: Easily acquire cookies for multiple platforms (Douyin, Bilibili, etc.) with real-time QR code display.

## Requirements

```bash
pip install nicegui playwright
playwright install
```

## Running

Run the following command from the project root:

```bash
python3 web_ui/nice_app.py
```

The app will start at `http://localhost:8080`.

## Architecture

- **Frontend**: NiceGUI (Vue.js based, Python backend).
- **Cookie Logic**: Calls `1_pre_processing/cli_tools/bk_get_cookies.py` as a subprocess.
- **Data**: Reads directly from `configs/` and `storage/`.
