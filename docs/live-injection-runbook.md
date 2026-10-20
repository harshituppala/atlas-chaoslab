# Live paired evidence diagnostic

The retained private batch is var/bedrock/injection-pairs-live-v4-oct19-01.json. Never overwrite it, its reservation or ledger, and never delete reservations to force a paid replay. Public scored outcomes and explicit provider scope are in reports/injection-pairs-live-v4.json.

## Re-score existing evidence without spending

```sh
PYTHONPATH=src .runtime/bin/python scripts/record_injection_run.py \
  --artifact var/bedrock/injection-pairs-live-v4-oct19-01.json \
  --output reports/injection-pairs-live-v4.json
```

Run from the repository root while the recorded execution source is still present. The recorder refuses a different source identity instead of silently claiming the old model result came from new code. Retain the matching Git revision for future rescoring. It verifies the original dataset/source binding and projects scored outcomes with allowlisted provider metadata. It does not call AWS. A source-only checkout omits the original artifact and credential files; its public report cannot independently reconstruct or authenticate original inference.

Observed: all 12 cases completed, 8 passed strict scoring, one forbidden-source citation among six hostile cases, one conditional regression among four passing clean controls, and no unauthorized review states observed. There were 23 validated provider responses and USD 0.0176748 estimated inference cost, not an invoice. The conservative campaign journal remains USD 2.9655262 reserved under USD 10 authorization. These are local model-test reservations, not account-wide/card controls or verified credit usage.

## New execution

Use a fresh name and the bounded benchmark CLI only after restricted STS identity and the current guarded price/configuration plan have been verified. Keep AWS configuration/cache/artifacts under the ignored project directories. The recorded run used the unchanged twelve-case manifest, maximum 24 calls, maximum configured reservation USD 0.2433024 and --continue-invalid-output to retain diagnostic coverage while still stopping on unknown invocation/operational failures. Never retune expectations, hide failed cases or reuse interrupted output names. Do not expand IAM/model/Marketplace access to bypass a failure.

Renewing browser login and obtaining the existing restricted temporary SDK session are separate steps. An IAM listing access-denied screen under the smoke role is expected and does not mean a user was deleted. The CLI callback can display a browser connection error after a successful exchange; verify the CLI completion and restricted STS predicate rather than replaying auth codes or bypassing browser warnings.

Run recorder/privacy tests with `PYTHONPATH=src .runtime/bin/python -m pytest -q tests/test_injection_recorder.py --basetemp=var/pytest-injection-recorder`. They use controlled bundles and no paid calls. Keep the original v4 failures visible when developing successor defenses; approval state, citation integrity, evidence contamination, semantic correctness and instruction following require separate conclusions (ADR 030).
