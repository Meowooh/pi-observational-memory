"""Export aggregate evidence only; never copy credentials or full task transcripts."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from harbor_agent import rows


def summarize(trial):
    result = json.loads((trial / "result.json").read_text())
    agent = trial / "agent"
    usage = json.loads((agent / "usage.json").read_text())
    meter = rows(agent / "meter.ndjson")
    sessions = [r for p in (agent / "sessions").glob("*.jsonl") for r in rows(p)]
    pack = [r for p in (agent / "sessions").glob("**/observation-pack/ledger.jsonl") for r in rows(p)]
    debug = [r for p in (agent / "observational-memory/debug").glob("*.ndjson") for r in rows(p)]
    tool_results = [r["message"] for r in sessions if r.get("type") == "message" and r.get("message", {}).get("role") == "toolResult"]
    tool_counts = Counter(r.get("toolName") for r in tool_results)
    configuration = next(r["data"] for r in meter if r["event"] == "configuration")
    active = [r["data"] for r in meter if r["event"] == "active_tools"]
    required = {"read", "write", "edit", "bash", "recall"}
    if usage["arm"] != "original":
        required.add("update_plan")
    if usage["arm"] in ("combined", "pack"):
        required.add("obs_recall")
    valid_tools = bool(active) and all(required <= set(names) for names in active)
    states = [r["data"] for r in sessions if r.get("customType") == "sol-pi-online-context-state-v1"]
    plan_boundaries = sum(bool((r.get("details") or {}).get("boundary")) for r in tool_results if r.get("toolName") == "update_plan")
    worker_errors = [r for r in debug if r["event"].endswith(".stream_error")]
    events = Counter(r["event"] for r in meter)
    main_responses = [r["data"] for r in meter if r["event"] == "main.usage"]
    return {
        "job": trial.parent.name,
        "trial": trial.name,
        "reward": (result.get("verifier_result") or {}).get("rewards", {}).get("reward"),
        "exception": (result.get("exception_info") or {}).get("exception_type"),
        **usage,
        "valid_tools": valid_tools,
        "workers_drained": events["shutdown.drained"] > 0,
        "infrastructure_interrupted": not main_responses or main_responses[-1].get("stopReason") == "error",
        "configuration": configuration,
        "tool_counts": dict(tool_counts),
        "plan_updates": tool_counts["update_plan"],
        "completed_plan_boundaries": plan_boundaries,
        "compactions": events["compaction.complete"],
        "compaction_failures": events["compaction.failed"],
        "packed_objects": len({r["id"] for r in pack if r["event"] == "placeholder"}),
        "placeholder_replays": sum(r["event"] == "placeholder" for r in pack),
        "estimated_replay_tokens_avoided": sum(r.get("removedTokens", 0) for r in pack),
        "pack_recalls": sum(r["event"] == "recall" for r in pack),
        "worker_errors": len(worker_errors),
        "worker_error_kinds": dict(Counter(r["event"] for r in worker_errors)),
        "main_error_responses": sum(r["event"] == "main.usage" and r["data"].get("stopReason") == "error" for r in meter),
        "final_online_state": {k: states[-1][k] for k in ("epoch", "requestCount", "completedBoundaryRequestCounts", "lastContextTokens", "positiveContextDeltaTotal", "positiveContextDeltaCount", "nativeCompactionCount", "cacheDebtTokens", "cacheDebtRepaymentTokens")} if states else None,
        "peak_provider_context_tokens": max((sum(r["data"]["usage"].get(k, 0) for k in ("input", "cacheRead", "cacheWrite", "output")) for r in meter if r["event"] == "main.usage"), default=0),
        "large_bash_output_files": sum(bool((r.get("details") or {}).get("fullOutputPath")) for r in tool_results),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    reports = [summarize(p.parent) for p in sorted(args.jobs.glob("luna-bottle-*-valid-*/*/result.json")) if (p.parent / "agent/usage.json").exists()]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(reports, indent=2) + "\n")
    columns = ["job", "arm", "reward", "infrastructure_interrupted", "configured_price_usd", "api_price_equivalent_usd", "input", "cacheRead", "output", "elapsed_sec", "plan_updates", "completed_plan_boundaries", "compactions", "packed_objects", "placeholder_replays", "estimated_replay_tokens_avoided", "pack_recalls", "worker_errors", "valid_tools", "workers_drained"]
    with (args.output / "results.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(reports)
    print(json.dumps([{k: r[k] for k in columns} for r in reports], indent=2))


if __name__ == "__main__":
    main()
