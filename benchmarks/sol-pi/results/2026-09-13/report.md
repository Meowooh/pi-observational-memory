# Pi Observational Memory + SoL-Pi：Luna 实测记录

2026-09-13。接入已跑通：保持 Observer、Reflector、Dropper 默认配置时，计划边界触发的 compaction 能使用 OM 摘要，并继续执行后续模型请求。现有结果仍不能证明“计划压缩 + ObservationPack”能稳定降低使用成本。首轮短任务里，组合组平均估算费用比原始 OM 高 10.5%；追加长任务里，计划组费用较低，但三组都未通过任务判分，组合组还达到超时上限。

已在 [OM fork](https://github.com/Meowooh/pi-observational-memory/tree/feat/sol-pi-benchmark) 接入可独立关闭的 OM 主动压缩触发开关，并提供 SoL-Pi 组合配置和可复现脚本。Observer、Reflector、Dropper 的配置保持默认。

实际运行使用本机 Pi 0.85.1、`pingcap/gpt-5.6-luna`、主模型 medium reasoning、worker 默认 low reasoning。该 provider 是用户原有的 OpenAI 兼容接口；官方 `openai-codex` 登录接口在初始冒烟成功后发生连接重置，因此正式对照使用现有 Luna 路线。报告验证的是这条配置的表现，未独立审计网关背后的模型路由。

首轮基准是 [Terminal-Bench 2.0 的 fix-code-vulnerability](https://github.com/harbor-framework/terminal-bench-2/tree/2fd12b88aafdd04a52c298e3940bcb189f9766d6/fix-code-vulnerability)：在 Bottle 项目中修复漏洞并生成报告。使用原始容器、原始任务指令和原始判分测试，官方参考解先通过判分。测试没有降低记忆或压缩阈值。它是单任务试验，不是完整 Terminal-Bench 得分。

| 配置 | 通过/有效运行 | 平均估算 $/次 | 两次成本范围 | 实际 compaction 次数 |
| --- | ---: | ---: | ---: | ---: |
| 原始 OM | 2/2 | 0.1291 | 0.1204–0.1377 | 0 |
| OM + 规划工具（对照） | 2/2 | 0.1245 | 0.1063–0.1427 | 0 |
| OM + 计划压缩 | 1/2 | 0.1383 | 0.1040–0.1726 | 0 |
| OM + 规划工具 + Pack | 1/2 | 0.1254 | 0.1044–0.1464 | 0 |
| OM + 计划压缩 + Pack | 2/2 | 0.1427 | 0.1242–0.1611 | 0 |

“OM + 规划工具”保留固定阈值压缩，但暴露相同的 `update_plan` 工具、规划提示和返回格式，用于区分规划本身与压缩机制。Pack 组同样包含该规划工具。原始 OM 对照不包含规划工具。组合组相对带规划工具的对照，本样本平均成本变化为 +14.6%。

成本包含主模型、Observer、Reflector、Dropper 和任何原生摘要调用。表中的美元数来自 Pi 配置费率：每百万 token，未缓存输入 $1、缓存读取 $0.10、输出 $6，缓存写入配置价 $1.25；不是已核对账单。本接口的 usage 中 cacheWrite 均报告为 0，不能据此确认网关没有其他写入收费。另提供按 [OpenAI Standard API 公开价格](https://developers.openai.com/api/docs/pricing)折算的列；本次短上下文下该折算数是上述配置价格的五分之一。输出已经包含 reasoning token，未重复加算。

| 配置 | 完成的计划边界 | 打包对象数 | 占位符替代重放次数 | 估算避免重放的 token | obs_recall 次数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原始 OM | 0 | 0 | 0 | 0 | 0 |
| OM + 规划工具（对照） | 6 | 0 | 0 | 0 | 0 |
| OM + 计划压缩 | 5 | 0 | 0 | 0 | 0 |
| OM + 规划工具 + Pack | 6 | 5 | 33 | 126,156 | 0 |
| OM + 计划压缩 + Pack | 6 | 6 | 39 | 144,592 | 0 |

首轮计划边界确实被记录，但这一轮所有有效运行中的主上下文 compaction 都是 0 次。最大一轮 provider context 约 33,436 token。因此首轮没有覆盖“压缩后继续工作”，也没有证明计划压缩能降低成本。OM 固定压缩阈值仍为 81,000 个估算源 token，Observer/Reflector 仍为默认的 10,000/20,000；这几个计数口径不同，不能直接当成同一个阈值。

ObservationPack 确实减少了大工具输出的重复重放。上表的避免重放 token 是 SoL-Pi 的本地估算，不等于账单节省。回读调用均为 0，因此频繁召回场景的额外成本也未被验证。OpenAI 的缓存要求渲染后的前缀匹配；替换历史可能影响缓存复用，所以应比较完整输入成本，而不能只比较压缩掉多少文本。[缓存说明](https://developers.openai.com/api/docs/guides/prompt-caching)

在这个样本中，成本还受不同执行路径、工具次数和后台 worker 调用影响。默认配置保持不变，并不意味着 worker 调用次数相同：Pack 会改变 provider 上下文的增长情况，而 OM 的调度可以使用 provider token 增量。成本差异不足以归因给某一项机制。

首轮保留了所有任务判分失败；没有重跑以取得通过分。计划压缩组第一次和 Pack 组补测的失败，都是漏洞报告分类标签未满足原测试要求；代码功能测试已通过。该次计划压缩为 0，不能将其失败归因于压缩丢失上下文。两次前台 429/503 中断的运行保留在原始数据中，但从完成率与平均成本比较中排除，并各安排了一次串行补测。早期白名单遗漏的四次调试运行也被排除。最初的 Cython 候选任务因官方参考解只通过 10/11 项检查，在获得任何成功模型样本前被换掉。

首轮初始对照使用两路并发；限流后原始 OM 对照和补测改为串行。部分完成的运行仍出现后台 worker 的 429/503。每组只有两个有效样本，运行顺序、服务波动和并发差异均限制结论，未进行统计显著性推断。不能据此宣称稳定节省固定百分比。

工程验证：OM 29 个测试文件、271 个测试通过；SoL-Pi 在官方锁定的 Pi 0.84.2 依赖下，18 个测试文件、139 个测试通过；类型检查、打包检查及公开 API 检查通过。测试适配层也通过针对本机 Pi 0.85.1 声明的类型检查。SoL-Pi 的高危级别依赖审计通过，开发测试依赖有 2 项 moderate 提示。新测试确认关闭 OM 主动压缩后，三个到期 worker 仍可运行。

首轮所有已记录用量的 Pi 调用（含调试、中断和两次成功冒烟）按各自配置价格估算合计约 $1.9260。有效对照之外的这些开销没有算入上表单次平均数。费用仅是 usage 与配置费率的估算。

复现版本和完整逐次数据见 [manifest.json](manifest.json)、[results.csv](results.csv)、[results.json](results.json) 和 [summary.json](summary.json)。SoL-Pi 固定在 `d7ecfc089944f0d04b80122a0a9a6ca0d786f3d0`，OM 基线固定在 `9f1cf4e2eeecd5bd1c49b8017d818e7cd07b65a0`。实现使用 SoL-Pi 默认经济系数 12.5 和 1,000-token 摘要估计，尚未针对 OM 的实际摘要大小校准。

以下是为覆盖真实 compaction 而追加的长任务检查；保持原有阈值，单独报告结果。

**MIPS 长任务检查：每组一次，独立于首轮结果**

使用同一 Terminal-Bench 版本的 [make-mips-interpreter](https://github.com/harbor-framework/terminal-bench-2/tree/2fd12b88aafdd04a52c298e3940bcb189f9766d6/make-mips-interpreter)：实现 JavaScript MIPS 解释器，运行 DOOM 并生成首帧。三组串行执行，沿用原任务 1,800 秒上限。没有降低任何 worker 或压缩阈值，也没有增加强制压缩提示。

| 配置 | 原始判分结果 | 估算 $/次 | 运行分钟 | compaction 次数 |
| --- | --- | ---: | ---: | ---: |
| OM + 规划工具（对照） | 未通过，0/3 项检查 | 1.0548 | 25.7 | 0 |
| OM + 计划压缩 | 未通过，1/3 项检查 | 0.6454 | 26.4 | 1 |
| OM + 计划压缩 + Pack | 30 分钟超时；0/3 项检查 | 0.8971 | 30.0 | 0 |

三组的任务 reward 均为 0。对照组未在测试要求的时间内生成首帧；计划组留下了图像文件，但启动输出和图像检查未满足要求；组合组在 agent 超时后执行原测试，仍未通过。超时属于保留的任务结果，未作为接口故障重新测试。

计划组这次运行费用比对照低 38.8%。两次执行路径和模型响应数量不同，且都未通过任务，因此该费用差不能用于估计成功完成任务后的节省比例。组合组这次记录的费用又比计划组高 39.0%，同时触及超时，不能据此认定两项叠加更好。

| 配置 | 主模型估算 $ | 后台 worker 及摘要估算 $ | 峰值 provider context token |
| --- | ---: | ---: | ---: |
| OM + 规划工具（对照） | 0.7641 | 0.2906 | 98,205 |
| OM + 计划压缩 | 0.4688 | 0.1767 | 49,571 |
| OM + 计划压缩 + Pack | 0.6560 | 0.2412 | 60,220 |

计划组实际发生 1 次 compaction，OM 提供的摘要约 661 个本地估算 token，没有额外的原生摘要模型调用。主上下文从约 38K 降至约 26K，其后记录了 47 次成功主模型响应。这验证了“计划边界触发 → OM 摘要 → 主流程续跑”可以工作，不能单凭续跑证明任务能力没有损失。

组合组的 Pack 实际替换了 6 个大工具输出，累计 435 次占位符重放替代，本地估算避免重放 2,041,545 token；这些不是账单节省 token。该组 compaction 为 0，说明两项开启并不意味着两项都会触发。`obs_recall` 为 0；模型也可以通过重新读取源文件取回信息，所以没有覆盖频繁主动召回时的完整开销。

三组 worker 参数均与首轮相同，模型均为 `pingcap/gpt-5.6-luna`。这次有 Observer 和 Reflector 的实际调用；Dropper 未达到运行条件，未强行触发。对照组与组合组各记录 2 条已恢复的非中止错误响应；计划组的 1 条中止响应与主动 compaction 对应，不能当作接口故障。三次运行均记录了后台任务结束标记，超时组私有日志与导出日志的用量及费用也一致；超时组费用仍仅代表该次尝试已记录的用量。

容器访问 GitHub release assets 连续失败，原始参考解的前两次检查未能启动 pytest。为恢复测试依赖，在参考解和三个模型组中一致预装 uv 0.9.5、Python 3.13.14；随后官方参考解通过全部 3 项检查。使用原始基础镜像，任务指令、参考解和判分脚本均未修改。依赖版本、下载 URL 和 SHA-256 见 [dependencies.json](long-task/dependencies.json)。这项环境准备以及 macOS arm64 上运行 linux/amd64 容器的条件，应随结果一起保留。

接入还有一个已确认的成本预测适配问题：Pi 在 OM 提供摘要时设置 `fromExtension=true`，而固定版本 SoL-Pi 的 `session_compact` 处理器会据此清零待回收的缓存成本。本次计划组压缩后，`cacheDebtTokens` 和 `cacheDebtRepaymentTokens` 确实都为 0。后续压缩决策因此没有继承这次估算的缓存重建成本；不能把当前组合视为已经完整适配 OM 的经济策略。[固定版本处理器](https://github.com/NVlabs/SoL-Pi/blob/d7ecfc089944f0d04b80122a0a9a6ca0d786f3d0/src/sol-pi/extensions/online-context-compact/extension.ts)

长任务记录费用合计约 $2.5973；加上首轮的调试、中断、冒烟和正式尝试，被测 Pi 的全部已记录模型费用约 $4.5233，仍是配置价格估算，并非已核对账单。长任务每组仅一次，且都未通过；不合并到首轮均值，不做统计显著性或稳定降本声明。

长任务的 [manifest.json](long-task/manifest.json)、[results.csv](long-task/results.csv)、[results.json](long-task/results.json)、[summary.json](long-task/summary.json) 和 [validation.json](long-task/validation.json) 包含复现版本、超时标记、成本分解与实际机制计数。执行适配代码固定于 `5f1c2a66daedc6eedb1863219d23d3598f8f3096`，分析代码固定于 `d16ad908aefd7380c9444bca5d58cde16737be80`。

目前可以确认的是：计划触发与 OM 摘要的接入能够续跑，Pack 能减少大输出的历史重放。整体省钱并保持任务完成率，尚无充分证据。代码保留为实验选项；进一步适配应处理 OM 摘要大小和缓存成本计账，并在模型能完成的长任务上做重复对照。
