import { appendFileSync } from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerStatusCommand } from "../../src/commands/status.js";
import { registerViewCommand } from "../../src/commands/view.js";
import { registerCompactionHook } from "../../src/hooks/compaction-hook.js";
import { registerCompactionTrigger } from "../../src/hooks/compaction-trigger.js";
import { registerConsolidationTrigger } from "../../src/hooks/consolidation-trigger.js";
import { Runtime } from "../../src/runtime.js";
import { registerRecallTool } from "../../src/tools/recall-observation.js";

export function registerMemoryAndMeter(pi: ExtensionAPI) {
	const runtime = new Runtime();
	registerConsolidationTrigger(pi, runtime);
	registerCompactionTrigger(pi, runtime);
	registerCompactionHook(pi, runtime);
	registerStatusCommand(pi, runtime);
	registerViewCommand(pi, runtime);
	registerRecallTool(pi);
	const log = (event: string, data: unknown) => appendFileSync(process.env.OM_BENCH_METER!, JSON.stringify({ ts: new Date().toISOString(), event, data }) + "\n");
	pi.on("session_start", (_event, ctx) => {
		runtime.ensureConfig(ctx.cwd);
		log("configuration", { config: runtime.config, model: ctx.model?.id, provider: ctx.model?.provider, sessionId: ctx.sessionManager.getSessionId() });
	});
	pi.on("message_end", event => {
		if (event.message.role === "assistant") {
			const { provider, model, usage, stopReason } = event.message;
			log("main.usage", { provider, model, usage, stopReason });
		}
	});
	pi.on("before_agent_start", () => {
		const tools = pi.getActiveTools();
		log("active_tools", tools);
		const required = ["read", "write", "edit", "bash", "recall"];
		if (process.env.OM_BENCH_ARM !== "original") required.push("update_plan");
		if (["pack", "combined"].includes(process.env.OM_BENCH_ARM!)) required.push("obs_recall");
		for (const name of required) if (!tools.includes(name)) throw new Error(`Benchmark tool is not active: ${name}`);
	});
	pi.on("session_before_compact", event => { log("compaction.request", { reason: event.reason, tokensBefore: event.preparation.tokensBefore }); });
	pi.on("session_compact", event => { log("compaction.complete", event); });
	pi.on("session_compact_failed", event => { log("compaction.failed", event); });
	// Print mode would otherwise terminate while a worker still owns a request.
	// This changes only test teardown, and is identical in every arm.
	pi.on("session_shutdown", async () => {
		await runtime.consolidationPromise;
		log("shutdown.drained", {});
	});
}
