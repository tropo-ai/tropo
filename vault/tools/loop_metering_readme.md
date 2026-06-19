# Loop Metering Gateway (v1.71 S1)

The Metering Gateway is the hard spend-kill for autonomous loops in Tropo. 
It uses `mitmproxy` to intercept Anthropic API calls, replacing a virtual key with the real key, and returns an HTTP 429 when the loop's `max_budget_usd` is reached. 
This guarantees the loop's policy agent cannot bypass the budget, as it never holds the real API key.

## Setup
1. Install mitmproxy: `brew install mitmproxy` or `pip install mitmproxy`.
2. Export your real key to the proxy's environment: `export REAL_ANTHROPIC_API_KEY="sk-ant-..."`
3. Configure the loop agent's environment (e.g., Claude Code) to use the proxy and a virtual key:
   ```bash
   export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
   export ANTHROPIC_API_KEY="sk-virtual-tropo-loop-run"
   ```

## Running
When starting a loop-run, launch the gateway alongside it, pointing it to the run folder:
```bash
mitmdump -s vault/tools/loop_metering_gateway.py --set loop_run_dir=vault/loop-runs/my-loop-run-123
```

The gateway will automatically read the `loop_contract_locked` event from `run.jsonl` to discover the `max_budget_usd`, enforce the virtual key, and write ground-truth spend to `gateway_spend.json` for the launchd watchdog.