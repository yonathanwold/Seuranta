# Seuranta V2 handoff

Continue on `team/app-v2`. The V2 review started from the latest remote `main` at `7d452a5` (full SHA `7d452a5de18a9ded219b79b2d7e04e776fc5cd32`). Fetch and inspect the current checkout before editing; do not treat that baseline as the latest V2 commit.

```sh
git fetch origin
git status --short --branch
git log --oneline --decorate -12
git rev-parse --short HEAD
npm install
npm test
npm run lint
npm run build
npm run dev -- --host 127.0.0.1 --port 4173
```

On Windows use `npm.cmd`. Read README, [the architecture](docs/frontend-architecture.md), [the demo guide](docs/demo-guide.md), and [the V2 review](docs/v2-review.md). Use the running app before changing it.

## Keep these boundaries

- Simulation starts with 20 anonymous sessions and four planned anchors. Live uses the same normalized provider contract and never falls back to simulation.
- Preserve scope matching, monotonic revisions, abort/generation guards, and heartbeat handling in the REST/WebSocket provider.
- The supplied uncompressed GLB remains the runtime asset; the Meshopt copy is retained.
- The first render is the complete building. Floor 1 is the operational cutaway; the other floors do not have telemetry.
- Room names, health, occupancy, event descriptions, and report values derive from the shared workspace model. Do not add per-page fixture data.
- Walkthrough uses the shared approximate navigation envelope. It is not surveyed wall collision. Preserve the centralized movement checks and coordinate transforms.
- Resolve is local demo state, not a backend mutation. Download snapshot JSON is a real local export. Enrollment is explicitly labeled as a demo acknowledgment.
- Keep anonymous IDs only. No names, MAC addresses, packet contents, or personal profiles.

## Remaining integration work

Measure the site and installed anchors, run the separate data-platform and positioning services, and validate scoped live snapshots and deltas against known physical points. This branch does not bundle Pi capture or backend services. Historical analytics, scheduled reports, replay, and upper-floor telemetry are not implemented. Three.js still produces the bundle-size advisory.

Use small conventional commits. Preserve teammate changes and do not merge, rewrite, or force-push other team branches. Push V2 with:

```sh
git push -u origin team/app-v2
```
