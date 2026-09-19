# USB Wi-Fi adapter requirements

For a monitor anchor, choose a Linux-supported USB adapter whose driver and
firmware expose all of the following on the target Pi kernel:

* monitor mode (`iw list` includes `* monitor`);
* Radiotap signal/RSSI metadata;
* the regulatory-domain channels required by the demo AP;
* stable channel locking without automatic roaming;
* a maintained in-kernel driver and reliable USB power behavior.

Prefer an adapter with an external antenna connector when the physical anchor
layout needs consistent directionality. Confirm the exact chipset/driver on
the Pi rather than relying on a vendor web listing. A USB power hub may be
needed for multiple adapters; validate it under sustained capture.

Do not use an adapter that requires a downloaded binary driver unless the
deployment owner has reviewed its provenance and update path. Do not enable
packet payload capture as a workaround for missing RSSI metadata.

The implementation has not tested any specific USB adapter or Raspberry Pi
kernel. Record adapter model, USB path, driver, firmware, country code, and
channel in the physical acceptance checklist.
