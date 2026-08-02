# Provider surface & prompt-caching economics: Anthropic direct vs OpenRouter

Research asset for wayfinder ticket **[Model routing: confirm the cheap/strong pair and the provider surface](https://github.com/msinghbehl/AI_PM_Learning_Bot/issues/5)**.
Grounded in primary docs fetched 2026-07-25.

## TL;DR

The earlier assumption that "OpenRouter doesn't pass through Anthropic prompt caching" is **wrong**. OpenRouter's provider-routing docs state explicitly that for Anthropic models, *"Prompt caching and extended context are enabled based on model capabilities"* — i.e. OpenRouter forwards `cache_control` to Anthropic and bills cache reads/writes at Anthropic's rates (the Models API exposes `input_cache_read` and `input_cache_write` price fields per model). So caching is **not** a differentiator between the two surfaces.

The real differentiators are: (1) a ~5% OpenRouter credit markup on top of upstream cost, (2) one extra network hop (latency), (3) OpenRouter's load-balancing/fallback across providers vs Anthropic's single endpoint, and (4) SDK shape — `anthropic` SDK with native `cache_control` + tool-use vs OpenAI-compatible `openai` SDK. For a bot expected to cost $3–6/mo, the markup is cents; the latency is tens of ms. The decision should rest on **operational simplicity and SDK ergonomics for the grader/critic**, not on caching.

## Anthropic prompt-caching facts (direct API)

Source: `platform.claude.com/docs/en/docs/build-with-claude/prompt-caching`.

### Pricing (per million tokens)

| Model | Base input | 5m cache write | 1h cache write | Cache read | Output |
|---|---|---|---|---|---|
| Claude Haiku 4.5 | $1.00 | $1.25 | $2.00 | **$0.10** | $5.00 |
| Claude Sonnet 4.6 | $3.00 | $3.75 | $6.00 | **$0.30** | $15.00 |
| Claude Opus 4.5 | $5.00 | $6.25 | $10.00 | **$0.50** | $25.00 |

Multipliers: 5m write = 1.25× base input; 1h write = 2× base; **cache read = 0.1× base** (90% off).

### Minimum cacheable prefix

- Haiku 4.5: **4,096 tokens** minimum
- Sonnet 4.6: **1,024 tokens** minimum

Below these thresholds the prefix is processed uncached with no error. Coach's shared context (rubric + curriculum node + lesson draft) will routinely exceed 1,024 tokens for Sonnet and likely 4,096 for Haiku, so caching is viable for the strong tier and marginal for the cheap tier.

### TTL

- Default 5-minute TTL, refreshed free on each hit.
- 1-hour TTL available at 2× write cost — useful for Coach's async pattern (user may not answer within 5 minutes).
- Cache is workspace-isolated; never shared across orgs.

### What Coach would cache

The strong-tier calls (critic, grader, regenerator) all share a large stable prefix:
- Tool definitions (grader tool, rubric schema)
- System prompt (grading instructions, rubric object)
- Curriculum node + lesson draft

This prefix is identical across grading calls within a session. With a 1h TTL, a daily 30-min session gets cache reads at 10% of base input on every strong-tier call after the first.

## OpenRouter facts

Source: `openrouter.ai/docs/guides/routing/provider-selection` + Models API.

### Prompt caching passthrough — CONFIRMED

> "OpenRouter manages some Anthropic features automatically: **Prompt caching and extended context are enabled based on model capabilities**."

The Models API exposes per-model `pricing.input_cache_read` and `pricing.input_cache_write` fields, confirming OpenRouter bills cache reads/writes (not just base tokens) for Anthropic models. So `cache_control` blocks pass through to Anthropic and you get the same 90% read discount.

**Caveat:** OpenRouter load-balances across providers by price. If you don't pin `provider.order: ["anthropic"]` or `only: ["anthropic"]`, a Claude request could route to a non-Anthropic provider variant that may not honor caching identically. To get deterministic caching through OpenRouter you must pin the provider.

### Pricing markup

OpenRouter charges credits against upstream cost. The markup is not published as a single number — it's baked into the per-model `pricing` shown on the models page, which reflects the top provider's price. For Anthropic models served by Anthropic, the displayed price is typically Anthropic's price **plus a ~5% credit overhead** (OpenRouter's margin). On a $3–6/mo spend this is $0.15–0.30/mo — negligible.

### Latency

One extra hop (client → OpenRouter → Anthropic). OpenRouter's own docs offer `sort: "latency"` and `:nitro` (throughput) routing. Typical added TTFT: tens of milliseconds. For an async Telegram bot where the user isn't watching a stream, this is immaterial. For the grader/critic (non-streaming, batch-ish), even more so.

### Fallback / load balancing

OpenRouter's default: load-balance across providers by inverse-square of price, fall back on 5xx/rate-limit. This is a **reliability win** over Anthropic direct (single endpoint). With `provider.order: ["anthropic"]` + `allow_fallbacks: true`, you get Anthropic first, fallback to other Claude hosts on outage.

### SDK shape

OpenAI-compatible (`openai` Python SDK with `base_url` override). No native `cache_control` field — you pass it as an `extra_body` parameter. Tool-use is translated. Structured outputs work via `response_format: json_schema` (Anthropic strict mode needs the `structured-outputs-2025-11-13` beta header, which OpenRouter forwards).

Anthropic direct uses the `anthropic` SDK: `cache_control` is a first-class field, tool-use is native, structured outputs are native.

## Modeled cost for Coach (daily 30-min session)

Assumptions from PLAN §4.1: ~80% cheap / 20% strong split. Per session, rough:
- Cheap tier (Haiku 4.5): ~5 calls, ~2k input + 500 output each = 10k in + 2.5k out
- Strong tier (Sonnet 4.6): ~2 calls, ~8k input (with cached prefix) + 1k output each = 16k in + 2k out

**Without caching (both surfaces):**
- Haiku: 10k × $1/M + 2.5k × $5/M = $0.010 + $0.0125 = $0.0225
- Sonnet: 16k × $3/M + 2k × $15/M = $0.048 + $0.030 = $0.078
- **Total: ~$0.10/session → ~$3/mo at 30 sessions**

**With caching (Sonnet 1h TTL, prefix ~6k tokens, 1 write + 1 read):**
- Sonnet input: 6k × $3.75/M (1h write) + 6k × $0.30/M (read) + 4k × $3/M (uncached tail) = $0.0225 + $0.0018 + $0.012 = $0.0363
- Sonnet output: 2k × $15/M = $0.030
- Sonnet total: $0.0663 (vs $0.078 uncached) → **~15% saving on the strong tier**
- Haiku: caching rarely viable (4,096-token minimum; calls are ~2k input) → no change
- **Total with caching: ~$0.088/session → ~$2.65/mo**

**OpenRouter markup on the cached scenario:** +5% ≈ +$0.004/session ≈ +$0.13/mo.

### Bottom line on savings

Caching saves roughly **$0.35–0.40/mo** at Coach's expected volume — real but small in absolute terms. The markup for OpenRouter is smaller still. **Cost is not the deciding factor between the two surfaces at this scale.**

## Performance hits

| Dimension | Anthropic direct | OpenRouter |
|---|---|---|
| TTFT latency | baseline | +tens of ms (one hop) |
| Caching | native, first-class | passthrough, but must pin `provider.only: ["anthropic"]` for deterministic cache hits |
| Tool-use / structured output | native | translated; strict mode needs beta header |
| Reliability / fallback | single endpoint | multi-provider fallback (win) |
| SDK ergonomics | `anthropic` SDK, `cache_control` first-class | `openai` SDK, `cache_control` via `extra_body` |
| Billing surface | separate from Task_IQ | shared with Task_IQ |

## Recommendation (revised)

The caching argument that previously favored Anthropic direct **does not hold** — OpenRouter passes it through. The decision now rests on:

1. **SDK ergonomics for the grader/critic.** Coach's strong tier does structured-output grading with tool-use and rubric schemas. The `anthropic` SDK handles this natively and cleanly; OpenRouter requires `extra_body` for `cache_control` and beta headers for strict structured outputs. For a bot whose entire quality thesis is "structure + verification," native structured-output + tool-use is a real ergonomic win.
2. **Operational simplicity.** One SDK, one auth, one set of docs. Coach is a Phase-1 validation project — fewer moving parts matters.
3. **Reliability is OpenRouter's one real advantage**, but at Coach's call volume (a handful of calls/day), a rare Anthropic outage is acceptable; the bot just retries via tenacity (already a ported pattern from Task_IQ per ticket #4).

**Recommendation stands: Anthropic direct for Phase 1**, keeping the `call_llm` wrapper provider-agnostic (per ticket #4) so OpenRouter remains a swap-in if reliability or multi-provider access becomes valuable in Phase 2. The earlier rationale (caching) is dropped; the new rationale is SDK ergonomics + operational simplicity at a scale where OpenRouter's reliability edge doesn't yet pay off.

## Open questions for the grilling

This research reframes but doesn't close ticket #5. The remaining decisions (cheap-tier model choice, strong-tier model choice, fallback policy) still need Manmeet's input. The provider decision is now lower-stakes than first framed.
