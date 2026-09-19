# PI-04: service install, outage behavior, and troubleshooting

## Install

```text
sudo install -d -o root -g root -m 0755 /opt/seuranta-edge
sudo cp -a edge/pi-agent/seuranta_edge /opt/seuranta-edge/
sudo install -d -o root -g root -m 0750 /etc/seuranta-edge
sudo install -d -o seuranta -g seuranta -m 0750 /var/lib/seuranta-edge
sudo install -m 0644 edge/pi-agent/systemd/seuranta-edge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now seuranta-edge.service
sudo systemctl status seuranta-edge.service
```

Copy a deployment-specific JSON config to `/etc/seuranta-edge/config.json` and
set `DEMO_RUN_SECRET` in a mode `0600` environment file. Do not use a checked-in
`.env`, shell history, or service command-line argument for the secret.

The supplied unit starts the agent's long-running `run` command. For a
no-hardware smoke test, use `--defaults mock-stream --count 3` interactively;
do not use the mock defaults in a physical deployment.

## Backend outage and recovery

The edge writes each batch to SQLite before attempting HTTP delivery. On an
outage, batches remain FIFO-ordered with their original IDs and retry using
bounded exponential backoff. Queue depth appears in heartbeats and
`buffer-status`. A full bounded queue raises `BUFFER_FULL` and the agent drops
new batches rather than growing without limit; resolve the outage promptly.

Recovery checklist:

1. `systemctl is-active seuranta-edge` is active.
2. `buffer-status` shows a nonzero depth during outage.
3. Restore backend connectivity and run `connectivity`.
4. Confirm depth decreases and heartbeat `observations_sent_total` increases.
5. Confirm no raw identifiers appear in logs or backend payloads.

## Troubleshooting

* `CAPTURE_COMMAND_MISSING`: install `iw`/`tcpdump` or choose `MOCK` for a
  no-hardware smoke test.
* `CAPTURE_PERMISSION`: grant only the service capabilities needed by the
  adapter; do not run the entire service as root without review.
* `WRONG_CHANNEL`: stop capture and lock the interface to the configured
  channel.
* `INACTIVE_SESSION`: the station has not completed explicit demo-network
  opt-in, or its session is silent/ended. This is expected privacy behavior.
* `BACKEND_UNAVAILABLE`: inspect URL, route, DNS, and firewall. Do not delete
  the SQLite file while trying to recover data.
* Monitor output is malformed or lacks Radiotap signal metadata: replace the
  adapter/driver or use AP-station mode; do not infer RSSI from payload bytes.

Hardware was not tested in this repository build.
