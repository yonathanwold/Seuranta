# PI-01: access-point anchor setup

This runbook configures a Raspberry Pi that is already serving the demo Wi-Fi
network. It uses `CAPTURE_STRATEGY=AP_STATIONS`, which reads associated-station
RSSI from `iw`; it does not inspect packet payloads.

## Before touching hardware

1. Flash a supported Raspberry Pi OS image and apply updates.
2. Connect Ethernet or the management network first. Keep the demo SSID and
   password out of source control and out of command output.
3. Install the standard tools: `python3`, `iw`, `ip`, `chrony`, and `systemd`.
4. Create a dedicated `seuranta` user and `/var/lib/seuranta-edge` owned by it.
5. Put the JSON config at `/etc/seuranta-edge/config.json` and provide
   `DEMO_RUN_SECRET` through a root-readable environment file with mode `0600`.

## Wi-Fi and channel lock

1. Set the AP SSID and country/regulatory domain using the Raspberry Pi OS
   networking system.
2. Lock the AP to the runbook channel before starting the agent. Do not let
   auto-channel selection change it during a run.
3. Confirm the interface and channel without printing station addresses:

   ```text
   iw dev wlan0 info
   iw dev wlan0 station dump | grep -E '^(Station|\s+signal:)'
   ```

   Compare the reported channel to `SEURANTA_WIFI_CHANNEL`. If the channel is
   wrong, stop and fix the AP configuration; do not silently accept samples.

## Agent setup

```text
install -d -o seuranta -g seuranta /var/lib/seuranta-edge
python3 -m venv /opt/seuranta-edge-venv   # optional; the agent itself has no third-party dependencies
python3 -m seuranta_edge --config-file /etc/seuranta-edge/config.json validate-config
python3 -m seuranta_edge --config-file /etc/seuranta-edge/config.json inspect-interface
python3 -m seuranta_edge --config-file /etc/seuranta-edge/config.json validate-channel
```

Use `AP_STATIONS` in the config. Start one service instance per run after the
run secret and backend URL have been set. The service must not run with a
committed secret.

## Physical validation record

Record date/time, Pi serial label, adapter/interface name, country code, SSID,
locked channel, backend URL, and the run identifier in the deployment log.
Then verify: a consenting test phone joins the SSID; `station dump` shows a
signal value; one `sample` or service cycle creates a valid batch; the backend
acknowledges it; and the queue depth returns to zero after delivery. Redact all
station addresses from the record.

Hardware was not tested in this repository build.
