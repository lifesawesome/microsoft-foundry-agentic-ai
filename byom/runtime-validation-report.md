# BYOM Validation Report

Date: 2026-11-16

## Summary

**Overall: PARTIAL. Offline verification passed; live Azure BYOM remains unverified.**

| Check | Result | Exit code | Evidence |
| --- | --- | --- | --- |
| Offline regression suite | PASS | 0 | 31 tests passed, zero failures or skips |
| Shared environment loading | PASS | 0 | 51 notebook configuration cells discover the root file from root and nested folders; BYOM defaults to that same file |
| Real OpenAI client with offline HTTP transport | PASS | 0 | Conversation, serialized agent reference, prompt, function call, submitted tool result, final answer, conversation deletion |
| Installed Foundry SDK contract inspection | PASS | 0 | Checked connection get, agent create/get/delete version signatures and prompt/function serialization |
| APIM policy | PASS locally | 0 | XML parse and assertions for named-value authentication and gateway-key removal; not deployed to APIM |
| Python lint | PASS | 0 | Ruff reported all checks passed |
| Editor diagnostics | PASS | n/a | No errors reported for the sample or tests |
| CLI startup | PASS | 0 | `--help` lists the documented options |
| Azure CLI account | Different context | 0 | Signed in, but the active tenant/subscription differ from the shared environment; account selection was not changed |
| Live sample configuration | BLOCKED | 1 | Shared project endpoint loads; `FOUNDRY_MODEL_DEPLOYMENT_NAME` is still unset; stopped before network access |
| Direct gateway inference | NOT RUN | n/a | No selected gateway URL/API key configured |
| Foundry -> gateway -> external model | NOT RUN | n/a | Connected-model reference is not configured and Azure CLI context must match the intended account |
| Gateway routing/log inspection | NOT RUN | n/a | Requires a live run against the intended APIM instance |

The live entry-point result was:

```text
FAIL: ValueError: Set FOUNDRY_MODEL_DEPLOYMENT_NAME to <connection-name>/<model-name>.
```

No Azure resources, Foundry connections, agent versions, or conversations were
created during validation. No inherited provider credentials were reused. The
required Foundry tooling prerequisite check installed its missing
`azure.ai.evaluations` azd extension; the sample itself does not use azd.

## Reproduce Local Checks

From the repository root, after installing the sample dependencies:

```powershell
python -m unittest discover -s byom -p test_byom.py -b -v
python scripts/check_environment.py
python -m ruff check scripts/check_environment.py byom/main.py byom/test_byom.py
python byom/main.py --help
```

Ruff is optional developer tooling, already present in the validation environment;
it is not a runtime dependency. The tests use the standard-library `unittest`
runner plus the sample's SDK dependencies. No Docker, database, browser, or hosted
agent runtime is required.

Verified terminal runtime: Windows, Python 3.13.17, `azure-ai-projects` 2.5.0,
`azure-identity` 1.25.3, `openai` 3.3.0, `python-dotenv` 1.2.3, and `httpx` 0.28.1.
This is not a claim that all Python versions or Azure regions were tested.

## Coverage And Limits

The offline suite covers endpoint/model validation, safe configuration mode,
credential-free connection lookup, wrong connection type, saved model read-back,
text-only and function-capable flows, untrusted tool names/arguments, incomplete
or incorrect answers, HTTP authentication failures, and cleanup after request,
conversation creation, or cleanup failures. It also checks `--keep` behavior.

The SDK wire test uses the real OpenAI client with an in-memory `httpx.MockTransport`.
Foundry management operations in the flow tests are mocked. These tests validate
client behavior and serialization, **not** cloud authentication, connection schema
acceptance, APIM policy compilation, provider compatibility, or network reachability.

## Complete Live Verification

Follow the [workshop setup](README.md) to create the dedicated APIM route and Foundry
model connection. Set `FOUNDRY_MODEL_DEPLOYMENT_NAME=<connection-name>/<model-name>`
in the shared repository-root `.env`. Store the APIM key
in the Foundry connection, not in this report.

```powershell
python byom/main.py --check-config
python byom/main.py --check-connection
python byom/main.py
```

For a complete pass, require exit code 0 from the full run, a passed tool-result
round trip without `--skip-tools`, successful temporary-resource cleanup, and
APIM diagnostics confirming the intended external backend. Optionally add
`--check-gateway` after configuring its local gateway credentials.

Do not treat mock output, a successful configuration check, or a direct gateway
probe as a passed end-to-end Foundry BYOM run.