"""
mitmproxy addon for Tropo-OS loop-run metering.
Usage: mitmdump -s vault/tools/loop_metering_gateway.py --set loop_run_dir=vault/loop-runs/...
"""
import json
import os
from mitmproxy import http
from pathlib import Path

class LoopMeteringGateway:
    def __init__(self):
        self.budget_usd = float('inf')
        self.spent_usd = 0.0
        self.run_dir = None
        self.real_api_key = os.environ.get("REAL_ANTHROPIC_API_KEY", "")
        self.model_pricing = {
            "claude-3-5-sonnet-20241022": (3.0, 15.0), # $3/M in, $15/M out
            "claude-3-5-haiku-20241022": (0.25, 1.25),
            "claude-3-opus-20240229": (15.0, 75.0)
        }
        self.req_models = {} # Track requested models by flow ID

    def load(self, loader):
        loader.add_option(
            name="loop_run_dir",
            typespec=str,
            default="",
            help="Path to the loop-run directory for reading contract and writing ground-truth spend",
        )

    def configure(self, updated):
        if "loop_run_dir" in updated and self.run_dir is None:
            import mitmproxy.ctx as ctx
            run_dir_str = ctx.options.loop_run_dir
            if run_dir_str:
                self.run_dir = Path(run_dir_str)
                self._load_contract()
                self._load_persisted_spend()

    def _load_contract(self):
        if not self.run_dir or not (self.run_dir / "run.jsonl").exists():
            return
        with open(self.run_dir / "run.jsonl", "r") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                    if ev.get("event") == "loop_contract_locked":
                        brakes = ev.get("brakes", {})
                        self.budget_usd = float(brakes.get("max_budget_usd", float('inf')))
                        break
                except Exception:
                    pass

    def _load_persisted_spend(self):
        """P2 fix: load persisted spend to survive proxy restarts."""
        spend_file = self.run_dir / "gateway_spend.json"
        if spend_file.exists():
            try:
                spend_data = json.loads(spend_file.read_text())
                self.spent_usd = float(spend_data.get("spent_usd", 0.0))
            except Exception:
                pass

    def request(self, flow: http.HTTPFlow):
        # 1. Enforce virtual key and inject real key
        if "api.anthropic.com" in flow.request.pretty_host:
            auth_header = flow.request.headers.get("x-api-key", "")
            if not auth_header.startswith("sk-virtual-tropo-"):
                flow.response = http.Response.make(
                    401, b"Unauthorized: Gateway requires a virtual key (sk-virtual-tropo-...).",
                    {"Content-Type": "text/plain"}
                )
                return
            if self.real_api_key:
                flow.request.headers["x-api-key"] = self.real_api_key

            # 2. Hard budget enforcement (P2 fix: BEFORE request completes)
            if self.spent_usd >= self.budget_usd:
                flow.response = http.Response.make(
                    429, b"Loop-run budget exceeded.",
                    {"Content-Type": "text/plain"}
                )
                return

            # Extract requested model for pricing
            try:
                if flow.request.content:
                    req_data = json.loads(flow.request.content)
                    model = req_data.get("model", "claude-3-5-sonnet-20241022")
                    self.req_models[flow.id] = model
            except Exception:
                pass

    def response(self, flow: http.HTTPFlow):
        if "api.anthropic.com" in flow.request.pretty_host and flow.response and flow.response.status_code == 200:
            try:
                data = json.loads(flow.response.content)
                usage = data.get("usage", {})
                
                # P1 fix: per-model pricing
                model = self.req_models.get(flow.id, data.get("model", "claude-3-5-sonnet-20241022"))
                in_price, out_price = self.model_pricing.get(model, (3.0, 15.0)) # Fallback to Sonnet
                
                in_tokens = usage.get("input_tokens", 0)
                out_tokens = usage.get("output_tokens", 0)
                cost = (in_tokens / 1_000_000 * in_price) + (out_tokens / 1_000_000 * out_price)
                self.spent_usd += cost
                
                # Write ground-truth to run_dir for the watchdog to read
                if self.run_dir:
                    spend_file = self.run_dir / "gateway_spend.json"
                    with open(spend_file, "w") as f:
                        json.dump({"spent_usd": self.spent_usd}, f)
            except Exception:
                pass
            finally:
                self.req_models.pop(flow.id, None)

addons = [LoopMeteringGateway()]

