# Contributing to Seuranta

Thanks for helping with the project. Seuranta is a frontend first, so a good change should be easy to run, easy to review, and honest about what is simulated.

## Before you start

Use the frontend branch and inspect it before editing:

```powershell
git fetch origin
git switch team/app
git pull --ff-only origin team/app
git status --short --branch
npm.cmd install
```

The edge, data-platform, and positioning branches have unrelated root histories. Do not merge them into `team/app`. Read `README.md`, `docs/frontend-architecture.md`, and `SEURANTA_CONTINUATION_PROMPT.md` before changing an integration contract.

For a focused change, create a short topic branch from `team/app` when your workflow allows it:

```powershell
git switch -c fix/short-description
```

Keep the topic branch based on the current `team/app` work. Push it normally and open a pull request back to `team/app`. Never force-push the shared team branches.

## Run and check the app

Simulation is the default and does not need a backend:

```powershell
npm.cmd run dev
```

Run the full local check before opening a pull request:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd audit --omit=dev
```

If you change UI behavior, also run the app and check the main Simulation flow: select a device, search for another device, try layers and camera controls, and make sure the browser console has no new app errors. Include a screenshot in the pull request when the change is visual.

## Code and style notes

- Keep backend DTO handling in `src/domain/adapters.ts` or the provider boundary. Components should use normalized camelCase types.
- Use `src/domain/coordinates.ts` for map/world conversion. Do not scatter axis or origin math through the scene.
- Keep provider output in the shared `ProviderSnapshot` shape so Mock and Live remain interchangeable.
- Prefer a small component or helper with a clear name over a clever one-liner. Existing files are compact, but readability matters more than matching every line style.
- Every visible button needs a real action. If a product surface is not implemented, leave it out instead of showing a dead control.
- Keep camera transitions explicit. Routine telemetry should not override a manual orbit or recenter the operator's view.
- Use anonymous, run-scoped session IDs only. Never add raw MACs, packet payloads, names, or personal profiles to fixtures, logs, screenshots, or UI copy.
- Preserve the adapter's tolerance for backend casing and wrappers, but do not silently accept an unscoped live delta.

## Pull request expectations

Please include:

- a short summary of the user-visible or integration change;
- the checks you actually ran and their results;
- screenshots or a short browser note for UI changes;
- whether the REST/WS contract changed and which docs were updated;
- a note confirming that no personal or raw device identifiers were added.

Keep commits focused and use a conventional prefix such as `feat(app):`, `fix(app):`, `test(app):`, or `docs(app):`. Do not add fake CI/deployment claims or change dependencies without explaining why.
