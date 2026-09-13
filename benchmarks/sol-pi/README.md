# OM + SoL-Pi experiment

This experiment keeps Observer, Reflector and Dropper at OM's defaults. It compares:

| Arm | OM source-token trigger | SoL-Pi Online Context Compact | ObservationPack |
| --- | --- | --- | --- |
| original | enabled | no planning tool | disabled |
| baseline | enabled | disabled | disabled |
| plan | disabled | enabled | disabled |
| pack | enabled | disabled | enabled |
| combined | disabled | enabled | enabled |

The four mechanism ablations expose the same `update_plan` schema, planning instructions and response format. The matched `baseline` records a plan without requesting compaction. The additional `original` arm omits that tool and its instructions to measure net planning overhead. Pack arms also expose `obs_recall`. The CLI explicitly allows these tools and logs their active names before a model request. OM's existing `recall` tool remains enabled. Pi's native context-pressure compaction remains enabled in all arms. OM renders summaries for either compaction owner.

SoL-Pi is loaded from the separate, pinned checkout in `manifest.json`. ActionFusion and Evidence-Preserving Reducer are not registered. Pack projects provider messages; OM continues to read the original session ledger. This is composition through public extension APIs, without vendoring or modifying Pi or SoL-Pi. The control's plan response follows NVIDIA's MIT-licensed SoL-Pi implementation.

## Reproduction

Requirements: local Pi 0.85.1, Node 22.19+ (tested on 26.7), Docker, RTK, Python 3.12 and `harbor==0.23.0`. Install this repository's locked development dependencies. Check out SoL-Pi and Terminal-Bench 2.0 at the exact commits in `manifest.json`; install SoL-Pi's locked dependencies with install scripts disabled.

Run the matrix with the Python interpreter where Harbor is installed:

```sh
rtk proxy python benchmarks/sol-pi/run_matrix.py \
  --workspace /absolute/path/to/experiment-work \
  --sol-root /absolute/path/to/SoL-Pi \
  --tasks-root /absolute/path/to/terminal-bench-2 \
  --auth-source /absolute/path/to/pi-agent-directory \
  --provider pingcap
```

The provider must already configure `gpt-5.6-luna` in Pi. The tested provider is the user's existing OpenAI-compatible route; no model substitution is performed. The launcher verifies repository revisions and Pi version, runs eight mechanism attempts and two original-OM controls serially, and writes machine-readable aggregate results. Initial live trials used pairs; rate-limit interruptions motivated the serial reproduction default. Do not reuse a workspace containing the same completed job names.

Harbor creates the original task container and executes the original verifier after the agent finishes. Pi runs on the host; `read`, `write`, `edit` and `bash` execute in the task container through Pi's public tool-operation interfaces. Full truncated shell outputs are copied into the container so the model can read the path returned by Pi. This adapter is intended for text-only tasks.

Credentials and live model logs stay in a separate host directory, outside Harbor's container-mounted agent logs. Only the selected provider's existing credential is copied, with restrictive permissions, and that copy is deleted at teardown. No global Pi settings are edited. Memory workers finish before teardown; this wait is identical in every arm and avoids losing background usage. Detailed sessions are retained locally; aggregate exports omit task transcripts and credentials.

## Accounting and limits

`worker.usage` records each Observer, Reflector and Dropper provider response once. Main responses and native summary usage are recorded separately; enclosing `turn_end` and `agent_end` events are never added again. Usage includes uncached input, cached input and output. `configured_price_usd` is Pi's calculation using the user's configured rates, not a verified invoice. `api_price_equivalent_usd` uses OpenAI Standard short-context rates ($0.20 input, $0.02 cached input, $0.25 explicit cache write, $1.20 output per million tokens). Reasoning tokens already included in output are not added twice. Long-context or non-Standard service tiers require different price calculations.

The economic gate retains SoL-Pi's default write/read ratio of 12.5 and its 1,000-token summary estimate. This estimate is not fitted to OM summaries. No threshold is lowered to manufacture compaction. Pack's estimated avoided replay tokens are not billed-token savings.

The manifest records task selection, failed infrastructure calibration and the decision to repeat every arm. A single task with two repetitions is a pilot, not a Terminal-Bench leaderboard score or a statistically reliable estimate of general savings. Report actual plan, compaction, packing and recall exposure alongside costs. A mechanism that never executes has not demonstrated a benefit.

`infrastructure_interrupted` marks attempts ending in an unrecovered provider error, even if the verifier happens to pass because required files were written earlier. Keep their spent tokens and costs in the raw results, but exclude them from completion/cost comparisons. The live experiment allows one serial replacement of each interrupted second repetition; task-quality failures are retained and are never rerun to obtain a passing score. Soft background-worker errors are recorded and remain a limitation of otherwise completed trials.
