"""Harbor 0.23 external agent using the host's Pi CLI and isolated Docker tools."""
import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.models.agent.context import AgentContext


ARMS = ("original", "baseline", "plan", "pack", "combined")


def rows(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a live writer may not have finished its last record
    return result


def collect_usage(root):
    records = []
    for row in rows(root / "meter.ndjson"):
        if row["event"] == "main.usage":
            records.append({"stage": "main", **row["data"]})
        elif row["event"] == "compaction.complete":
            entry = row["data"]["compactionEntry"]
            if entry.get("usage"):
                records.append({"stage": "native_summary", "usage": entry["usage"]})
    for path in (root / "agent-home/observational-memory/debug").glob("*.ndjson"):
        for row in rows(path):
            if row["event"] == "worker.usage":
                records.append(row["data"])
    totals = {k: 0 for k in ("input", "cacheRead", "cacheWrite", "output")}
    by_stage = {}
    configured_cost = 0.0
    for record in records:
        usage = record.get("usage") or {}
        configured_cost += usage.get("cost", {}).get("total", 0)
        stage = by_stage.setdefault(record["stage"], {"requests": 0, **{k: 0 for k in totals}})
        stage["requests"] += 1
        for key in totals:
            value = usage.get(key, 0)
            totals[key] += value
            stage[key] += value
    # OpenAI Standard short-context rates. OAuth quota is not dollar billing.
    estimate = (totals["input"] * .20 + totals["cacheRead"] * .02 + totals["cacheWrite"] * .25 + totals["output"] * 1.20) / 1_000_000
    return {"requests": len(records), **totals, "configured_price_usd": configured_cost, "api_price_equivalent_usd": estimate, "by_stage": by_stage}


class PiMemoryAgent(BaseAgent):
    def __init__(self, *args, arm="baseline", **kwargs):
        super().__init__(*args, **kwargs)
        if arm not in ARMS:
            raise ValueError(f"Unknown arm {arm}")
        self.arm = arm

    @staticmethod
    def name():
        return "pi-om-sol-pi"

    def version(self):
        return "0.85.1"

    async def setup(self, environment):
        # Pinned to Harbor 0.23; no credentials or host workspace are mounted.
        result = await environment._run_docker_compose_command(["ps", "-q", "main"])
        self.container = result.stdout.strip()
        if not self.container or any(c not in "0123456789abcdef" for c in self.container):
            raise RuntimeError("Could not resolve the Harbor task container")

    async def run(self, instruction, environment, context: AgentContext):
        bench = Path(__file__).resolve().parent
        sol = Path(os.environ["SOL_PI_ROOT"]).resolve() / "src/sol-pi/extensions"
        root = Path(os.environ["OM_BENCH_PRIVATE_ROOT"]) / str(uuid.uuid4())
        root.mkdir(mode=0o700, parents=True)
        agent_dir = root / "agent-home"
        agent_dir.mkdir(mode=0o700)
        provider = os.environ.get("OM_BENCH_PROVIDER", "openai-codex")
        auth = json.loads((Path(os.environ["OM_BENCH_AUTH_SOURCE"]) / "auth.json").read_text())
        (agent_dir / "auth.json").write_text(json.dumps({provider: auth[provider]}))
        (agent_dir / "auth.json").chmod(0o600)
        models_path = Path(os.environ["OM_BENCH_AUTH_SOURCE"]) / "models.json"
        if models_path.exists():
            configured = json.loads(models_path.read_text()).get("providers", {})
            if provider in configured:
                (agent_dir / "models.json").write_text(json.dumps({"providers": {provider: configured[provider]}}))
        settings = {
            "defaultProvider": provider, "defaultModel": "gpt-5.6-luna",
            "defaultThinkingLevel": "medium", "packages": [], "extensions": [],
            "telemetry": False,
            "compaction": {"enabled": True, "reserveTokens": 16384, "keepRecentTokens": 20000},
            "observational-memory": {"debugLog": True, "proactiveCompaction": self.arm not in ("plan", "combined")},
        }
        (agent_dir / "settings.json").write_text(json.dumps(settings, indent=2))
        (root / "sessions").mkdir()
        (root / "instruction.md").write_text(instruction)
        extension = root / "extension.ts"
        extension.write_text(f'''
import {{ registerMemoryAndMeter }} from {json.dumps(str(bench / "memory-and-meter.ts"))};
import {{ registerRemoteTools }} from {json.dumps(str(bench / "remote-tools.ts"))};
import {{ createObservationPackExtension }} from {json.dumps(str(sol / "observation-pack/index.ts"))};
import {{ registerOnlineContextCompact }} from {json.dumps(str(sol / "online-context-compact/index.ts"))};
import {{ registerOnlineTools }} from {json.dumps(str(sol / "online-context-compact/tools.ts"))};
import {{ analyzePlanTransition, formatPlanSnapshot, parsePlanSteps }} from {json.dumps(str(sol / "online-context-compact/plan.ts"))};
export default function(pi) {{
  registerMemoryAndMeter(pi);
  if ({json.dumps(self.arm)} === "pack" || {json.dumps(self.arm)} === "combined") createObservationPackExtension()(pi);
  if ({json.dumps(self.arm)} === "plan" || {json.dumps(self.arm)} === "combined") registerOnlineContextCompact(pi);
  else if ({json.dumps(self.arm)} !== "original") {{
    let previous = [];
    registerOnlineTools(pi, {{ updatePlan: async input => {{
      const steps = parsePlanSteps(input.steps);
      if (!steps?.length) throw new Error("Plan must contain at least one valid step");
      const transition = analyzePlanTransition(previous, steps);
      const ids = transition.completedSteps.map(step => step.id);
      previous = steps;
      return {{ content: [{{type: "text", text: [formatPlanSnapshot(steps), ...transition.advice].join("\\n")}}], details: {{boundary: ids.length > 0, completed_step_ids: ids, progress_recorded: ids.length > 0 && input.progress !== undefined, task_status: "active", plan: steps}} }};
    }} }});
  }}
  registerRemoteTools(pi);
}}
''')
        env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent_dir), "PI_TELEMETRY": "0", "OM_BENCH_CONTAINER": self.container, "OM_BENCH_ARM": self.arm, "OM_BENCH_METER": str(root / "meter.ndjson")}
        allowed_tools = "read,bash,edit,write" + (",update_plan" if self.arm != "original" else "") + ",recall" + (",obs_recall" if self.arm in ("pack", "combined") else "")
        args = ["rtk", "proxy", "pi", "--offline", "--provider", provider, "--model", "gpt-5.6-luna", "--thinking", "medium", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files", "--tools", allowed_tools, "-e", str(extension), "--session-dir", str(root / "sessions"), "--mode", "json", "--print", instruction]
        start = time.monotonic()
        process = None
        try:
            with (root / "pi.ndjson").open("w") as out, (root / "pi.stderr").open("w") as err:
                process = await asyncio.create_subprocess_exec(*args, cwd=root, env=env, stdout=out, stderr=err)
                while process.returncode is None:
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
                    usage = collect_usage(root)
                    context.n_input_tokens = usage["input"] + usage["cacheRead"] + usage["cacheWrite"]
                    context.n_cache_tokens = usage["cacheRead"]
                    context.n_output_tokens = usage["output"]
                    context.cost_usd = usage["configured_price_usd"]
            if process.returncode != 0:
                raise RuntimeError(f"Pi exited {process.returncode}; inspect pi.stderr")
            meter_rows = rows(root / "meter.ndjson")
            main_responses = [r["data"] for r in meter_rows if r["event"] == "main.usage"]
            if not any(r.get("stopReason") not in ("error", "aborted") for r in main_responses):
                raise RuntimeError("No successful model response; infrastructure failure, not a scored model attempt")
            if main_responses[-1].get("stopReason") == "error":
                raise RuntimeError("Final model request failed after retries; interrupted infrastructure attempt")
            if not any(r["event"] == "shutdown.drained" for r in meter_rows):
                raise RuntimeError("Missing worker-drain marker; cost accounting would be incomplete")
        finally:
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=20)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            usage = collect_usage(root)
            context.n_input_tokens = usage["input"] + usage["cacheRead"] + usage["cacheWrite"]
            context.n_cache_tokens = usage["cacheRead"]
            context.n_output_tokens = usage["output"]
            context.cost_usd = usage["configured_price_usd"]
            usage.update(arm=self.arm, elapsed_sec=time.monotonic() - start, exit_code=process.returncode if process else None)
            (root / "usage.json").write_text(json.dumps(usage, indent=2))
            context.metadata = {"arm": self.arm, "provider": provider, "cost_basis": "Pi configured prices, not a verified invoice; API equivalent separately recorded", "usage": usage}
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            for name in ("pi.ndjson", "pi.stderr", "meter.ndjson", "usage.json", "instruction.md"):
                if (root / name).exists():
                    shutil.copy2(root / name, self.logs_dir / name)
            for source, name in ((root / "sessions", "sessions"), (agent_dir / "observational-memory", "observational-memory")):
                if source.exists():
                    shutil.copytree(source, self.logs_dir / name, dirs_exist_ok=True)
            (agent_dir / "auth.json").unlink(missing_ok=True)
            (agent_dir / "models.json").unlink(missing_ok=True)
