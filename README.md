# PixelAir for Home Assistant

A Home Assistant custom integration for PixelAir devices (Fluora, Monos, and more) by Light+Color.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=acvigue&repository=homeassistant-pixelair&category=integration)

## Features

- Automatic device discovery on your local network
- Light entity with brightness, color (HS), and effects support
- Push-based state updates for responsive UI
- Efficient state_counter polling (only fetches state when changes detected)

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots menu in the top right corner
3. Select **Custom repositories**
4. Add `acvigue/homeassistant-pixelair` as a repository with category **Integration**
5. Click **Add**
6. Search for "PixelAir" in HACS
7. Click **Download**
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/acvigue/homeassistant-pixelair/releases)
2. Extract and copy the `custom_components/pixelair` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **PixelAir**
4. The integration will automatically discover devices on your network
5. Select the device you want to add
6. Done!

## Supported Devices

- Fluora
- Monos
- Additional PixelAir devices as they become available

## Troubleshooting

### No devices found

- Ensure your PixelAir device is powered on and connected to the same network as Home Assistant
- Check that UDP broadcast traffic is allowed on your network
- Verify no firewall is blocking UDP ports 48899 and 48900

### Debug logging

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.pixelair: debug
    libpixelair: debug
```

## License

MIT License - see LICENSE file for details.
