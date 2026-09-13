import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import { createBashTool, createEditTool, createReadTool, createWriteTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Host credentials never enter the benchmark container; only tool operations do. */
export function registerRemoteTools(pi: ExtensionAPI) {
	const container = process.env.OM_BENCH_CONTAINER;
	if (!container || !/^[a-f0-9]{12,64}$/.test(container)) throw new Error("Missing benchmark container ID");
	const local = process.cwd();
	const remote = "/app";
	const map = (path: string) => path === local ? remote : path.startsWith(local + "/") ? remote + path.slice(local.length) : path;

	function exec(args: string[], input?: string): Promise<Buffer> {
		return new Promise((resolve, reject) => {
			const child = spawn("rtk", ["proxy", "docker", "exec", "-i", "-w", remote, container!, ...args], { stdio: ["pipe", "pipe", "pipe"] });
			const out: Buffer[] = [], err: Buffer[] = [];
			child.stdout.on("data", chunk => out.push(chunk));
			child.stderr.on("data", chunk => err.push(chunk));
			child.on("error", reject);
			child.on("close", code => code === 0 ? resolve(Buffer.concat(out)) : reject(new Error(Buffer.concat(err).toString() || `Remote operation exited ${code}`)));
			child.stdin.end(input);
		});
	}
	const read = {
		readFile: (p: string) => exec(["cat", "--", map(p)]),
		access: async (p: string) => { await exec(["test", "-r", map(p)]); },
		detectImageMimeType: async () => null,
	};
	const write = {
		writeFile: async (p: string, text: string) => { await exec(["python3", "-c", "import sys; open(sys.argv[1], 'wb').write(sys.stdin.buffer.read())", map(p)], text); },
		mkdir: async (p: string) => { await exec(["mkdir", "-p", "--", map(p)]); },
	};
	pi.registerTool(createReadTool(local, { operations: read }));
	pi.registerTool(createWriteTool(local, { operations: write }));
	pi.registerTool(createEditTool(local, { operations: { ...read, ...write } }));
	const bash = createBashTool(local, { operations: {
		exec: (command, cwd, { onData, signal, timeout }) => new Promise((resolve, reject) => {
			if (signal?.aborted) return reject(new Error("aborted"));
			const seconds = Math.min(timeout ?? 120, 300);
			const child = spawn("rtk", ["proxy", "docker", "exec", "-w", map(cwd), container!, "timeout", "--kill-after=5s", `${seconds}s`, "bash", "-lc", command], { stdio: ["ignore", "pipe", "pipe"] });
			child.stdout.on("data", onData);
			child.stderr.on("data", onData);
			const abort = () => child.kill("SIGTERM");
			signal?.addEventListener("abort", abort, { once: true });
			child.on("error", reject);
			child.on("close", code => {
				signal?.removeEventListener("abort", abort);
				if (signal?.aborted) reject(new Error("aborted"));
				else if (code === 124) reject(new Error(`timeout:${seconds}`));
				else resolve({ exitCode: code });
			});
		}),
	} });
	pi.registerTool({
		...bash,
		async execute(id, params, signal, onUpdate) {
			const result = await bash.execute(id, params, signal, onUpdate);
			const source = result.details?.fullOutputPath;
			if (!source) return result;
			const target = `/tmp/${basename(source)}`;
			await write.writeFile(target, await readFile(source, "utf8"));
			return {
				...result,
				content: result.content.map(block => block.type === "text" ? { ...block, text: block.text.replaceAll(source, target) } : block),
				details: { ...result.details, fullOutputPath: target },
			};
		},
	});
	pi.on("session_start", () => pi.setActiveTools(["read", "write", "edit", "bash", ...(process.env.OM_BENCH_ARM !== "original" ? ["update_plan"] : []), "recall", ...(process.env.OM_BENCH_ARM?.includes("pack") || process.env.OM_BENCH_ARM === "combined" ? ["obs_recall"] : [])]));
	pi.on("before_agent_start", event => ({
		systemPrompt: event.systemPrompt.replaceAll(local, remote) + "\n" + (process.env.OM_BENCH_ARM !== "original" ? "Use update_plan to track a concise working plan; update it at meaningful completed stages with progress evidence. " : "") + "Complete the task in this session. All file and shell tools operate in the Linux task container. Do not access hidden benchmark tests or reference solutions.",
	}));
}
