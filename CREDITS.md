# CREDITS — Knowledge Base Sources

This curriculum was authored using a corpus of sources fed to an ingestion agent. The agent proposed concept nodes grounded in cited primary sources; Manmeet reviewed, edited, and committed the final curriculum. This file credits the openly-licensed and public-reference sources that shaped the curriculum.

**Attribution principle:** every concept node in `curriculum/ai-technical-fluency.yaml` cites its primary sources directly (URL + anchor). This file is the higher-level credit roll for sources whose licenses permit public attribution of their use. Sources read locally but not redistributed (LinkedIn posts, practitioner blog posts, course lessons) are not named here — they're recorded in the local `sources/` provenance only.

## Primary sources (model creators + cited research)

These are the ground-truth sources the curriculum cites directly. Every concept node references ≥1 of these. All are public reference material or openly distributable.

| Source | URL | License | Used for |
|--------|-----|---------|----------|
| Anthropic — Claude model family | https://www.anthropic.com/claude | Public reference (publisher ToS) | Context windows, safety, tool use, model cards |
| OpenAI — GPT-4 technical report | https://openai.com/research/gpt-4 | Public reference (publisher ToS) | Training pipeline, evals, model card |
| Google DeepMind — Gemini | https://deepmind.google/technologies/gemini/ | Public reference (publisher ToS) | MoE architecture, long context, multimodal |
| Vaswani et al. (2017) — "Attention Is All You Need" | https://arxiv.org/abs/1706.03762 | arXiv (public distribution) | Transformer architecture |
| OpenAI (2022) — InstructGPT / RLHF paper | https://arxiv.org/abs/2203.02155 | arXiv (public distribution) | RLHF, alignment, training pipeline |
| Karpathy — LLM Wiki gist | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f | Shared openly by author for reuse | LLM Wiki pattern, knowledge compounding |

## Openly-licensed secondary sources (GitHub repos)

These repos are MIT/Apache licensed and credited here. Their content was read locally by the ingestion agent; the repos themselves are publicly forkable.

| Source | URL | Author | License | Used for |
|--------|-----|--------|---------|----------|
| Generative AI Course | https://github.com/AbdullahAbuHassann/GenerativeAICourse | AbdullahAbuHassann | MIT | LLMs, prompt engineering, RAG, agents, MCP, fine-tuning, evaluation, LLMOps |
| Generative AI for Beginners | https://github.com/microsoft/generative-ai-for-beginners | Microsoft | MIT | 18-lesson course — prompting, RAG, LLM fundamentals, agents, evals, responsible AI |
| Agents Towards Production | https://github.com/NirDiamant/agents-towards-production | NirDiamant | MIT | Production agent patterns — guardrails, memory, multi-agent, observability, evaluation |

## Reference framework (public job descriptions)

Public job postings used by the critic for completeness gap-checking. These are public reference material.

| Source | Used for |
|--------|----------|
| 10 AI PM job descriptions (Apple, DeepMind, IBM, Intel, Meta, NVIDIA, OpenAI, Salesforce, Tesla, Uber) | Reference framework — what hiring managers probe |
| AI PM Interview Guidance (8 categories of technical questions) | Reference framework — interview question surface |

## Local-only sources (not credited here)

Sources read locally by the ingestion agent but not redistributed (LinkedIn posts, practitioner blog posts, locally-authored synthesis docs) are recorded in the local `sources/` directory provenance only. They are not named in this public file because their content is not licensed for redistribution. The curriculum's per-node citations point at the primary sources these materials *pointed at*, not at the materials themselves.

## License of this curriculum

The curriculum YAML in `curriculum/ai-technical-fluency.yaml` is authored by Manmeet Singh Behl. The concept structure, prerequisite DAG, difficulty tags, and challenge types are original work. Concept descriptions are grounded in the cited primary sources; where a description paraphrases a source, the source is cited.

This work is licensed under [MIT](LICENSE) (to be added). The cited sources retain their respective licenses.
