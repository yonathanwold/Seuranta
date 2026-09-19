# Clock synchronization and per-run secret setup

## Clock synchronization

Use chrony or the site-approved NTP service on every Pi. Verify
`chronyc tracking` and the agent `time-sync` command before each run. All wire
timestamps are RFC3339 UTC and observations also carry Unix milliseconds.

If the heartbeat reports `CLOCK_SKEW`, stop cross-anchor comparisons, correct
NTP, and begin a fresh run if timestamps were already produced. The agent does
not silently change captured times.

## Per-run secret

Generate a new random secret for every demo run (at least 16 UTF-8 bytes; 32
random bytes is preferred):

```text
umask 077
openssl rand -hex 32 | sudo tee /etc/seuranta-edge/run-secret >/dev/null
```

Provide that value as `DEMO_RUN_SECRET` through the deployment secret store or
an environment file mode `0600`. Do not commit it, put it in a JSON example,
write it to a ticket, or include it in diagnostic output. The same run secret
must be configured on all participating anchors so a device receives the same
temporary HMAC ID across anchors. Rotate it before the next run; never reuse a
prior run secret.

The implementation keeps raw station tokens in memory only while an active
opted-in session is mapped. Temporary IDs are uppercase Base32 and are not
persistent device identifiers.
