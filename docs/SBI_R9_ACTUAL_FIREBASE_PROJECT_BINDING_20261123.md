# SBI R9 — Actual Firebase Staging Project Binding (23 November 2026)

## User-provided Firebase Console evidence
On 23 November 2026, the project owner provided screenshots displaying:
- Dedicated Firebase project name **SBI R9 Staging**, project ID **`sbi-r9-staging`**, on **Spark**.
- **Authentication → Sign-in method → Email/Password = Enabled**.

These are user-visible console observations, not independent provider API verification. **No Firebase connector or secure staging runtime identity is connected to this QA workspace yet.** No live signed-token test has been performed.

## Development-only application source alignment
Previous R8/R9 code used historical synthetic project prefix `sbi-r8-staging-...`. That synthetic prefix must not accidentally be used in a real staging run.

Updated R8 staging WSGI launcher **and** the opt-in R9 signed-token QA gate to require exact project ID **`sbi-r9-staging`**. Updated staging-origin prefix **`https://sbi-r9-staging-...`** while retaining explicit HTTPS requirement. Historical variable names `SBI_R8_STAGING_*`, prior commit hashes, service mode guard and private staging storage layout remain unchanged; this commit does not change production `app.py` or `dashboard_sessions.py`.

- R8 staging negative tests additionally reject the obsolete synthetic project.
- R9 signed-token preflight tests additionally reject the obsolete synthetic project and hostname.
- R9 ADC protection still requires exact project match `sbi-r9-staging` AND actual service-account identity `sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com`. The identity has **not** been created or confirmed.
- Registration of a dedicated QA Firebase **Web app** and access to its separately scoped API key remain pending; do not commit keys, passwords, tokens or real SBI data to GitHub.
- Creating or deploying any staging HTTPS origin, cloud runtime or IAM service account requires separate secure connection, billing/permission review and owner authorization. Do not create real test users until these gates are satisfied.
- R9 live probe is **not run by GitHub CI**. All GitHub tests here use synthetic data, localhost test clients or networkless Docker isolation.

## Release restrictions
Production Firebase project `meghraj-reconciliation`, live Lightsail/Caddy routes, original finance data, production GitHub `main` and **Financial Apply** remain unchanged/locked. Do not interpret login-provider activation as completion of real signed-token verification. Outstanding external gate: [issue #148](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/148).
