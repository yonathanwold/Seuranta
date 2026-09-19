# PI-02: monitor-mode anchor setup

Use this runbook for an anchor that listens with a separate monitor-capable
interface. Set `CAPTURE_STRATEGY=MONITOR`. A monitor adapter must be separate
from the AP interface unless the AP can tolerate a temporary mode change.

## Adapter and driver gate

Before installation, verify that the USB adapter supports monitor mode and
Radiotap RSSI reporting on the target Raspberry Pi kernel. Check only the
interface capabilities; do not collect a packet capture:

```text
iw phy phy0 info | sed -n '/Supported interface modes:/,/Band/p'
iw list | sed -n '/Supported interface modes:/,/Band/p'
```

The output must include `* monitor` and the driver must expose signal metadata.
If the adapter exposes only managed mode, use PI-01 or replace the adapter.

## Configure and lock

1. Stop network-manager roaming/auto-channel behavior for the monitor
   interface.
2. Set the country/regulatory domain and lock the monitor interface to the AP
   channel using the OS network tool.
3. Verify `iw dev mon0 info` reports the configured channel.
4. Verify the agent's `validate-channel` command passes.

The collector invokes a constrained metadata-only command and does not save a
pcap. Do not add `-w`, payload filters, or packet files to the service.

## Test sequence

1. Start a consenting test device on the demo network.
2. Run `sample` and confirm an RSSI observation is generated.
3. Stop the test device and confirm no new active-session observation is made.
4. Disconnect the backend, generate a sample, and confirm SQLite depth grows.
5. Restore the backend and confirm FIFO delivery and depth recovery.

Hardware was not tested in this repository build.
