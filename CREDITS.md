# CREDITS — Knowledge Base Sources

This curriculum was authored using a corpus of sources fed to an ingestion agent. The agent proposed concept nodes grounded in cited primary sources; Manmeet reviewed, edited, and committed the final curriculum. This file credits every source that contributed to the knowledge base.

**Attribution principle:** every concept node in `curriculum/ai-technical-fluency.yaml` cites its primary sources directly (URL + anchor). This file is the higher-level credit roll — who created the materials that shaped the curriculum, and where to find them.

## Primary sources (model creators + cited research)

These are the ground-truth sources the curriculum cites directly. Every concept node references ≥1 of these.

| Source | URL | License | Used for |
|--------|-----|---------|----------|
| Anthropic — Claude model family | https://www.anthropic.com/claude | Publisher ToS (reference) | Context windows, safety, tool use, model cards |
| OpenAI — GPT-4 technical report | https://openai.com/research/gpt-4 | Publisher ToS (reference) | Training pipeline, evals, model card |
| Google DeepMind — Gemini | https://deepmind.google/technologies/gemini/ | Publisher ToS (reference) | MoE architecture, long context, multimodal |
| Vaswani et al. (2017) — "Attention Is All You Need" | https://arxiv.org/abs/1706.03762 | arXiv (public distribution) | Transformer architecture |
| OpenAI (2022) — InstructGPT / RLHF paper | https://arxiv.org/abs/2203.02155 | arXiv (public distribution) | RLHF, alignment, training pipeline |
| Karpathy — LLM Wiki gist | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f | Shared openly by author for reuse | LLM Wiki pattern, knowledge compounding |

## Secondary sources (practitioner-authored course material)

These supplemented the primary sources with depth, examples, and practitioner perspective. Not committed to the repo (not licensed for redistribution); the agent read them locally.

| Source | URL | Author | Used for |
|--------|-----|--------|----------|
| Generative AI Course | https://github.com/AbdullahAbuHassann/GenerativeAICourse | AbdullahAbuHassann | LLMs, prompt engineering, RAG, agents, MCP, fine-tuning, evaluation, LLMOps |
| Generative AI for Beginners | https://github.com/microsoft/generative-ai-for-beginners | Microsoft | 18-lesson course — prompting, RAG, LLM fundamentals, agents, evals, responsible AI |
| Agents Towards Production | https://github.com/NirDiamant/agents-towards-production | NirDiamant | Production agent patterns — guardrails, memory, multi-agent, observability, evaluation |
| GPT-5.6 family analysis | https://simonwillison.net/2026/Jul/9/gpt-5-6/ | Simon Willison | Model report reading, context windows, cost economics |
| AI PM Knowledge Store & Deep Multi-Hop Extraction Plan | (local synthesis doc) | Manmeet Singh Behl | Synthesis of LLM Wiki, RAG vs fine-tuning, frontier models, evals |

## Tertiary sources (LinkedIn saves — pointers to primary/secondary)

LinkedIn posts that pointed at the primary and secondary sources above. Recorded as provenance ("Manmeet encountered this concept via X's post"); the posts themselves are not citations.

| Source | Author | Category |
|--------|--------|----------|
| Vibe Coding Essentials | Maria R | AI PM Skills |
| OpenAI/Anthropic PM Requirements | Aakash Gupta | AI PM Skills |
| Prompt Engineering Courses | Sumon Kabir | Free Resources |
| Stanford AI Curriculum | Sairam Sundaresan | Free Resources |
| 10 Free GitHub Repos | Ghadeer A | Free Resources |
| Opus-4.6 Breakdown | Maria R | Claude Code |
| Claude Optimization | Chorouk Malmoum | Claude Code |
| AI PM Interview Prep | singhashutosh05 | Career Advice |
| Salary Benchmarks | Pawel Huryn | Career Advice |

## Reference framework (not ingested as concepts)

Used by the critic for completeness gap-checking — cross-referenced against the proposed concepts to flag gaps.

| Source | Used for |
|--------|----------|
| 10 AI PM job descriptions (Apple, DeepMind, IBM, Intel, Meta, NVIDIA, OpenAI, Salesforce, Tesla, Uber) | Reference framework — what hiring managers probe |
| AI PM Interview Guidance (8 categories of technical questions) | Reference framework — interview question surface |

## License of this curriculum

The curriculum YAML in `curriculum/ai-technical-fluency.yaml` is authored by Manmeet Singh Behl. The concept structure, prerequisite DAG, difficulty tags, and challenge types are original work. Concept descriptions are grounded in the cited primary sources; where a description paraphrases a source, the source is cited.

This work is licensed under [MIT](LICENSE) (to be added). The cited sources retain their respective licenses.
