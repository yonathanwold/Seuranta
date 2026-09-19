# PI-03: monitor channel and clock validation

This procedure is the pre-run acceptance gate for monitor anchors.

## Channel gate

Run the following while the AP is active and before an opt-in session begins:

```text
iw dev mon0 info
python3 -m seuranta_edge --config-file /etc/seuranta-edge/config.json validate-channel
```

The channel must equal `SEURANTA_WIFI_CHANNEL`. Re-run after a five-minute
observation window; if it changed, mark the anchor `DEGRADED`, stop capture,
and fix channel locking.

## Clock gate

Enable chrony or the site-approved NTP service. Then run:

```text
chronyc tracking
python3 -m seuranta_edge --config-file /etc/seuranta-edge/config.json time-sync
```

The CLI reports synchronized only when the best-effort offset is at most two
seconds. A clock-skew heartbeat warning is diagnostic only; it does not rewrite
observation timestamps. Fix time before comparing anchors.

## Acceptance evidence

Keep a redacted checklist with the UTC time, interface, configured channel,
observed channel, offset, and operator initials. Never paste station addresses,
MACs, packet output, or run secrets into the checklist.

Hardware was not tested in this repository build.
