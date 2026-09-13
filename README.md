# QIVICON for Home Assistant 0.5.0

Experimental local Home Assistant integration for the QIVICON Home Base 2 / Aurora firmware.

The integration logs in to the Home Base with its **device password**, extracts the short-lived Aurora access token and service gateway ID, and calls the local JSON-RPC endpoint. It does not use a Telekom cloud account.

## Confirmed against the test Home Base

- Device-password login at `/system/http/login`
- Bearer token and `QIVICON-ServiceGatewayId` extraction
- Authenticated JSON-RPC at `/remote/json-rpc`
- System, rooms, devices and openHAB-style item inventory
- Automatic re-login when the API rejects an expired session
- Local polling every 30 seconds

## Known supported devices

The following devices have been identified from a real Home Base inventory.
Their availability and values naturally depend on the Home Base seeing them online.

- Signify Netherlands B.V. `dimmable_light`: a single light with brightness.
- Lidl/Livarno Lux `TS0502A` (`_TZ3000_49qchf10`): a tunable-white light with brightness and colour-temperature controls.
- Tuya `extended_color_light` (`_TZ3000_odygigth`): a full-colour light with brightness, colour picker and colour-temperature controls.
- Sercomm `DT_ESW02_001`: a DECT outdoor plug exposed as a switch.
- eQ-3 `HMIP-PSM`: a Homematic IP switching and metering plug. Its primary switch, energy measurements and communication error are exposed; virtual channels, schedules and profile controls are omitted.
- EUROtronic `DT_HKR_461_03_RF_460_03`: heating thermostat with measured and target temperature. It was offline in the inspected inventory, so write commands remain unverified.
- EUROtronic `DT_DWS_458_04`: four-action wall switch. Its battery state is exposed; use event capture to identify its transient button events before device triggers can be added.
- Huawei/Silabs `EM3587 EZSP SPI`: the internal Zigbee coordinator. It exposes status, firmware and communication timestamps as diagnostics. The six frame-counter items are omitted because the Home Base reports them as `NULL`.

## Install with HACS

1. In HACS, open **Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/inv1sible/ha-qivicon` with category **Integration**.
4. Find **QIVICON**, download it and restart Home Assistant.
5. Open **Settings → Devices & services → Add integration → QIVICON**.
6. Enter the Home Base IP address and its device password.

## Install manually

1. Copy `custom_components/qivicon` into the Home Assistant configuration directory under `custom_components/qivicon`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → QIVICON**.
4. Enter only the Home Base IP address and its device password.

TLS certificate verification is always disabled internally because the Home Base uses a self-signed certificate for `qivicon.ip`.

The password is stored in the Home Assistant config entry, as is customary for local device integrations. Protect Home Assistant backups accordingly.

## Current entity mapping

- Read-only numeric/string items become sensors.
- Read-only switch/contact items become binary sensors.
- Writable switch items tagged as controls become switches.
- Writable light channels belonging to the same device are combined into one
  light entity with brightness, color-temperature and HS color controls as
  advertised by QIVICON.
- Other writable numeric items become number entities with the advertised range and step.
- Writable strings with advertised values become select entities.
- Other writable strings become text entities.
- Writable date/time items become datetime entities.
- A controllable temperature item paired with a measured temperature item becomes a climate entity.
- Offline QIVICON devices make their entities unavailable.
- Infrastructure counters and known internal Homematic IP channels are suppressed so they do not clutter the device page.

Every entity exposes the raw item name, type, tags, writable flag, range, step and options as state attributes. This keeps newly encountered capabilities inspectable even before a specialized Home Assistant mapping exists.

The `qivicon.send_item_command` service can send a raw command to any item by its exact `qivicon_item` attribute. It is intended as an escape hatch for capabilities that do not yet have a specialized entity.

Home Assistant's **Download diagnostics** action exports the complete non-secret system, room, device and item inventory. Access tokens, cookies and the device password are never included.

## Capture button and other transient events

The normal inventory cannot contain momentary button presses. To record the raw
QIVICON event stream for device analysis:

1. Open **Developer tools → Actions** in Home Assistant.
2. Run `qivicon.start_event_capture` with a duration from 10 to 600 seconds
   (120 seconds by default).
3. Operate the buttons or sensors that need analysis during that period.
4. Wait until the duration has elapsed, or run `qivicon.stop_event_capture`.
5. Download the QIVICON integration diagnostics and inspect `event_capture`.

The capture retains at most 500 events in memory and is cleared whenever a new
capture starts or Home Assistant restarts. Credential-like fields are redacted
before they enter the diagnostic buffer.

## Experimental command support

Switch, light and thermostat commands use the openHAB-style item command route through QIVICON's authenticated REST proxy. Inventory and reads are confirmed. A live dimmer command was successfully sent and its original value restored. Thermostat control still needs a controlled test before it should be relied upon.

## Development status

This is an experimental custom integration distributed through a HACS custom repository. Event/WebSocket updates, options, reauthentication UI, richer color-light mappings and automated Home Assistant runtime tests remain future work.

The API approach follows the authentication and JSON-RPC structure described in Luca Glockow's 2017 bachelor thesis, *Sicherheitsanalyse einer Smarthome-Zentrale*, updated by inspecting the current Aurora frontend.
