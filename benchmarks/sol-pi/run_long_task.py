"""Run the separately reported MIPS exposure check, serially and without tuning thresholds."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--sol-root", type=Path, required=True)
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--auth-source", type=Path, required=True)
    parser.add_argument("--provider", default="pingcap")
    parser.add_argument("--oracle-job", type=Path)
    parser.add_argument("--verifier-dependencies", type=Path)
    args = parser.parse_args()
    bench = Path(__file__).resolve().parent
    manifest = json.loads((bench / "manifest.json").read_text())
    for folder, expected in ((args.sol_root, manifest["sol_pi_commit"]), (args.tasks_root, manifest["task_commit"])):
        actual = subprocess.check_output(["rtk", "proxy", "git", "-C", str(folder), "rev-parse", "HEAD"], text=True).strip()
        if actual != expected:
            raise SystemExit(f"Unexpected revision: {folder}")
    version = subprocess.check_output(["rtk", "proxy", "pi", "--version"], text=True).strip()
    if version != manifest["pi_version"]:
        raise SystemExit(f"Expected Pi {manifest['pi_version']}; got {version}")
    work = args.workspace.resolve()
    work.mkdir(parents=True, exist_ok=True)
    private = work / "private-runs"
    private.mkdir(mode=0o700, exist_ok=True)
    env = {
        **os.environ,
        "DOCKER_DEFAULT_PLATFORM": "linux/amd64",
        "OM_BENCH_HARBOR_CACHE": str(work / "harbor-cache"),
        "OM_BENCH_PRIVATE_ROOT": str(private),
        "OM_BENCH_AUTH_SOURCE": str(args.auth_source.resolve()),
        "OM_BENCH_PROVIDER": args.provider,
        "SOL_PI_ROOT": str(args.sol_root.resolve()),
    }
    if args.verifier_dependencies:
        env["OM_BENCH_VERIFIER_DEPS"] = str(args.verifier_dependencies.resolve())

    async def run(name, agent):
        config = {
            "job_name": name, "jobs_dir": str(work / "jobs"),
            "n_concurrent_trials": 1, "n_attempts": 1, "quiet": True,
            "agents": [agent],
            "tasks": [{"path": str((args.tasks_root / "make-mips-interpreter").resolve())}],
        }
        job = work / "jobs" / name
        if job.exists():
            raise SystemExit(f"Refusing to overwrite existing job: {job}")
        path = work / f"{name}.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        with (work / f"{name}.log").open("w") as log:
            process = await asyncio.create_subprocess_exec(sys.executable, str(bench / "run_harbor.py"), "run", "--config", str(path), env=env, stdout=log, stderr=log)
            code = await process.wait()
        results = list(job.glob("*/result.json"))
        if code or len(results) != 1:
            raise RuntimeError(f"Harbor job did not produce one result: {name}; exit {code}")
        result = json.loads(results[0].read_text())
        print(f"{name}: reward={(result.get('verifier_result') or {}).get('rewards')}; exception={(result.get('exception_info') or {}).get('exception_type')}", flush=True)
        return job, result

    if args.oracle_job:
        oracle_results = list(args.oracle_job.glob("*/result.json"))
        if len(oracle_results) != 1:
            raise SystemExit("Expected exactly one completed oracle result")
        oracle = json.loads(oracle_results[0].read_text())
    else:
        agent = {"import_path": "verifier_dependencies:PreparedOracle", "kwargs": {"task_dir": str((args.tasks_root / "make-mips-interpreter").resolve())}} if args.verifier_dependencies else {"name": "oracle"}
        _, oracle = await run("luna-mips-oracle", agent)
    if oracle.get("exception_info") or (oracle.get("verifier_result") or {}).get("rewards", {}).get("reward") != 1:
        raise SystemExit("Official oracle did not pass; no model trials started")

    from harbor_agent import rows
    for arm in ("baseline", "plan", "combined"):
        agent = {"import_path": "harbor_agent:PiMemoryAgent", "model_name": f"{args.provider}/gpt-5.6-luna", "kwargs": {"arm": arm}}
        for attempt in (1, 2):
            job, result = await run(f"luna-mips-{arm}-valid-1" + ("-retry" if attempt == 2 else ""), agent)
            meter = next(job.glob("*/agent/meter.ndjson"), None)
            responses = [r["data"] for r in rows(meter) if r["event"] == "main.usage"] if meter else []
            exception = (result.get("exception_info") or {}).get("exception_type")
            final_provider_error = bool(responses) and responses[-1].get("stopReason") == "error"
            if exception == "AgentTimeoutError" or not final_provider_error:
                break
            if attempt == 1:
                print(f"{arm}: one permitted replacement after final provider interruption", flush=True)
                await asyncio.sleep(30)
    subprocess.run([sys.executable, str(bench / "analyze.py"), str(work / "jobs"), str(work / "results"), "--pattern", "luna-mips-*-valid-*/*/result.json"], check=True)


if __name__ == "__main__":
    asyncio.run(main())
