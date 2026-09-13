import type { AgentEvent } from "@earendil-works/pi-agent-core";
import { debugLog } from "../debug-log.js";

/** One record per completed provider response, including tool-call responses. */
export function logWorkerUsage(stage: "observer" | "reflector" | "dropper", event: AgentEvent): void {
	if (event.type !== "message_end" || event.message.role !== "assistant") return;
	const { provider, model, usage, stopReason } = event.message;
	if (!usage) return;
	debugLog("worker.usage", { stage, provider, model, usage, stopReason });
}
