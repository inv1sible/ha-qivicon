# Changelog

## 0.6.0 — Experimental event-driven updates

- Replaces the regular 30-second polling interval with a persistent QIVICON
  remote-event subscription.
- Loads the complete QIVICON snapshot on integration startup and after an event
  subscription has recovered. Normal state changes cause an event-triggered,
  briefly debounced refresh.
- Automatically retries a failed event subscription and records its status,
  errors, reconnects and refresh timing in integration diagnostics.
- Does not create additional Home Assistant entities or states for transport
  diagnostics.

This event-driven mode is experimental. Please live-test every available device
type, especially contacts, motion sensors, switches, dimmable and colour lights,
thermostats, buttons and offline/reconnected devices, before relying on it for
automations.
