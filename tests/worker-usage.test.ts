import { describe, expect, it, vi } from "vitest";

vi.mock("../src/debug-log.js", () => ({ debugLog: vi.fn() }));
import { debugLog } from "../src/debug-log.js";
import { logWorkerUsage } from "../src/agents/usage.js";

describe("worker usage accounting", () => {
	it("counts a tool-call response once and ignores duplicate enclosing events", () => {
		vi.mocked(debugLog).mockClear();
		const usage = { input: 10, output: 2, cacheRead: 30, cacheWrite: 0 };
		const message = { role: "assistant", provider: "openai-codex", model: "gpt-5.6-luna", usage, stopReason: "toolUse" };
		logWorkerUsage("observer", { type: "message_end", message } as any);
		logWorkerUsage("observer", { type: "turn_end", message } as any);
		logWorkerUsage("observer", { type: "agent_end", messages: [message] } as any);
		logWorkerUsage("observer", { type: "message_end", message: { role: "toolResult" } } as any);
		expect(debugLog).toHaveBeenCalledExactlyOnceWith("worker.usage", {
			stage: "observer", provider: "openai-codex", model: "gpt-5.6-luna", usage, stopReason: "toolUse",
		});
	});
});
