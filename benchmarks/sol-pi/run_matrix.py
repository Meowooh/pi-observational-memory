"""Reproduce the bounded two-repeat experiment with the existing local Pi login."""
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
    args = parser.parse_args()
    bench = Path(__file__).resolve().parent
    manifest = json.loads((bench / "manifest.json").read_text())
    for folder, commit in ((args.sol_root, manifest["sol_pi_commit"]), (args.tasks_root, manifest["task_commit"])):
        actual = subprocess.check_output(["rtk", "proxy", "git", "-C", str(folder), "rev-parse", "HEAD"], text=True).strip()
        if actual != commit:
            raise SystemExit(f"Unexpected revision for {folder}: {actual}; expected {commit}")
    version = subprocess.check_output(["rtk", "proxy", "pi", "--version"], text=True).strip()
    if version != manifest["pi_version"]:
        raise SystemExit(f"This harness was validated with Pi {manifest['pi_version']}; found {version}")
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    private = workspace / "private-runs"
    private.mkdir(mode=0o700, exist_ok=True)
    env = {
        **os.environ,
        "DOCKER_DEFAULT_PLATFORM": "linux/amd64",
        "OM_BENCH_HARBOR_CACHE": str(workspace / "harbor-cache"),
        "OM_BENCH_PRIVATE_ROOT": str(private),
        "OM_BENCH_AUTH_SOURCE": str(args.auth_source.resolve()),
        "OM_BENCH_PROVIDER": args.provider,
        "SOL_PI_ROOT": str(args.sol_root.resolve()),
    }
    task = str((args.tasks_root / manifest["task"]).resolve())
    for repeat, pairs in [(1, [("baseline", "combined"), ("pack", "plan")]), (2, [("plan", "pack"), ("combined", "baseline")]), (1, [("original",)]), (2, [("original",)])]:
        async def run(arm):
            name = f"luna-bottle-{arm}-valid-{repeat}"
            config = {
                "job_name": name, "jobs_dir": str(workspace / "jobs"),
                "n_concurrent_trials": 1, "n_attempts": 1, "quiet": True,
                "agents": [{"import_path": "harbor_agent:PiMemoryAgent", "model_name": f"{args.provider}/gpt-5.6-luna", "kwargs": {"arm": arm}}],
                "tasks": [{"path": task}],
            }
            path = workspace / f"{name}.json"
            path.write_text(json.dumps(config, indent=2))
            with (workspace / f"{name}.log").open("w") as log:
                process = await asyncio.create_subprocess_exec(sys.executable, str(bench / "run_harbor.py"), "run", "--config", str(path), env=env, stdout=log, stderr=log)
                code = await process.wait()
            print(f"{name}: process exit {code}; see {name}.log", flush=True)
        for pair in pairs:
            for arm in pair:
                await run(arm)
    subprocess.run([sys.executable, str(bench / "analyze.py"), str(workspace / "jobs"), str(workspace / "results")], check=True)


if __name__ == "__main__":
    asyncio.run(main())
