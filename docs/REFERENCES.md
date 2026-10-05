# References

Credits for Ekbasis: the ideas it builds on, the models and data it uses or is compared with, and the tools it runs
on. Each entry ends with what we used it for. All entries were checked against their sources on 2026-10-03 (see
[Verification notes](#verification-notes)).

## Ideas we built on

- Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux (ISBN 978-0-374-27563-1).
  https://us.macmillan.com/books/9780374533557/thinkingfastandslow/ — fast vs. deliberate thinking; the System One
  framing.
- LeCun, Y. (2022). *A Path Towards Autonomous Machine Intelligence* (version 0.9.2, 2022-06-27). Position paper,
  OpenReview. https://openreview.net/forum?id=BZ5a1r-kVsf — JEPA, and the world-model module (predicting the next state
  given an action) that Ekbasis implements.
- Assran, M., et al. (2023). *Self-Supervised Learning from Images with a Joint-Embedding Predictive Architecture*
  (I-JEPA). CVPR 2023, pp. 15619–15629. https://doi.org/10.1109/CVPR52729.2023.01499 — the JEPA-style hindsight loss.
- Bardes, A., et al. (2024). *Revisiting Feature Prediction for Learning Visual Representations from Video* (V-JEPA).
  Transactions on Machine Learning Research (TMLR). https://arxiv.org/abs/2404.08471 — the JEPA-style hindsight loss.
- Ha, D., & Schmidhuber, J. (2018). *World Models*. arXiv. https://arxiv.org/abs/1803.10122 · *Recurrent World Models
  Facilitate Policy Evolution*. NeurIPS 2018. https://arxiv.org/abs/1809.01999 — learned world models.
- Hafner, D., et al. (2020). *Dream to Control: Learning Behaviors by Latent Imagination* (Dreamer). ICLR 2020.
  https://arxiv.org/abs/1912.01603 — planning in a learned model.
- Schrittwieser, J., et al. (2020). *Mastering Atari, Go, chess and shogi by planning with a learned model* (MuZero).
  Nature 588, 604–609. https://doi.org/10.1038/s41586-020-03051-4 — planning with a learned model.
- Guo, C., et al. (2017). *On Calibration of Modern Neural Networks*. ICML 2017 (PMLR 70, pp. 1321–1330).
  https://arxiv.org/abs/1706.04599 — calibration and expected calibration error (ECE).
- Geifman, Y., & El-Yaniv, R. (2017). *Selective Classification for Deep Neural Networks*. NIPS 2017 (Advances in
  Neural Information Processing Systems 30). https://arxiv.org/abs/1705.08500 — answering only when confident and
  escalating the rest.
- Kalman, R. E. (1960). *A New Approach to Linear Filtering and Prediction Problems*. Journal of Basic Engineering
  82(1), 35–45. https://doi.org/10.1115/1.3662552 — predict, observe, correct.
- Wolpert, D. M., Ghahramani, Z., & Jordan, M. I. (1995). *An Internal Model for Sensorimotor Integration*. Science
  269(5232), 1880–1882. https://doi.org/10.1126/science.7569931 — the forward model: predicting the consequence of an
  action before it lands.
- Wolpert, D. M., & Kawato, M. (1998). *Multiple paired forward and inverse models for motor control*. Neural Networks
  11(7–8), 1317–1329. https://doi.org/10.1016/S0893-6080(98)00066-5 — one part chooses the action, another predicts its
  consequence (paired inverse and forward models).
- Li, K., et al. (2023). *Emergent World Representations: Exploring a Sequence Model Trained on a Synthetic Task*.
  ICLR 2023. https://arxiv.org/abs/2210.13382 — internal world-state representations.
- Greenblatt, R., et al. (2024). *AI Control: Improving Safety Despite Intentional Subversion*. ICML 2024 (PMLR 235,
  pp. 16295–16336; arXiv 2023). https://arxiv.org/abs/2312.06942 — trusted monitoring of a stronger, untrusted model's
  actions.

## Looking when unsure: prior work

"Look when unsure" (`simulate(observe=...)`) applies a known idea to a language world model; these are its closest
precedents and neighbors.

- Trimpe, S., & D'Andrea, R. (2014). *Event-Based State Estimation With Variance-Based Triggering*. IEEE Transactions
  on Automatic Control 59(12), 3266–3281.
  https://ethz.ch/content/dam/ethz/special-interest/mavt/dynamic-systems-n-control/idsc-dam/Research_DAndrea/Balancing%20Cube/TAC14b_web.pdf
  — measuring when the predictor's own uncertainty crosses a threshold; the schedules it produces become periodic.
- Holt, S., Hüyük, A., & van der Schaar, M. (2023). *Active Observing in Continuous-time Control*. NeurIPS 2023
  (Advances in Neural Information Processing Systems 36).
  https://proceedings.neurips.cc/paper_files/paper/2023/hash/9050e8d5b5de08d16e65dc79ad5c0146-Abstract-Conference.html
  — a learned model that observes when its uncertainty crosses a threshold; observing at regular intervals is not
  optimal.
- Frauenknecht, B., Subhasish, D., Solowjow, F., & Trimpe, S. (2025). *On Rollouts in Model-Based Reinforcement
  Learning* (Infoprop). ICLR 2025.
  https://proceedings.iclr.cc/paper_files/paper/2025/hash/be7a642a92de108a57e4d50866144d73-Abstract-Conference.html —
  tracking the error accumulated along a model rollout.
- Levis, P., Clausen, T., Hui, J., Gnawali, O., & Ko, J. (2011). *The Trickle Algorithm*. RFC 6206, IETF (Standards
  Track). https://www.rfc-editor.org/rfc/rfc6206.html — the checks' backoff: the interval doubles while all is
  consistent and goes back to the minimum after an inconsistency.
- Jiang, Z., et al. (2023). *Active Retrieval Augmented Generation* (FLARE). EMNLP 2023.
  https://arxiv.org/abs/2305.06983 — a language model that consults the world (retrieves) when it is unsure.
- Ren, A. Z., et al. (2023). *Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners*
  (KnowNo). CoRL 2023. https://arxiv.org/abs/2307.01928 — multiple-choice likelihoods deciding when to ask for help.
- Song, X., & Cai, Z. (2026). *Ask the World Before Acting: Environment Probing for Calibrated Agent World Models*.
  arXiv. https://arxiv.org/abs/2606.31422 — language agents deciding when to probe the environment; self-reported
  uncertainty fails under confident wrong beliefs, as Ekbasis' confidence does on its rare errors in familiar worlds.
- Zuo, Y., et al. (2026). *Qwen-AgentWorld: Language World Models for General Agents*. arXiv.
  https://arxiv.org/abs/2606.24597 — language world models for agents that reason at length before predicting;
  Ekbasis answers in one pass.

## How the release checkpoint was made

- Ross, S., Gordon, G. J., & Bagnell, J. A. (2011). *A Reduction of Imitation Learning and Structured Prediction to
  No-Regret Online Learning* (DAgger). AISTATS 2011, PMLR 15, pp. 627–635. https://arxiv.org/abs/1011.0686 — training
  on the states the model itself visits: the items r4a mined inside V42's own chains.
- Venkatraman, A., Hebert, M., & Bagnell, J. A. (2015). *Improving Multi-Step Prediction of Learned Time Series Models*
  (Data as Demonstrator). AAAI 2015, 29(1), pp. 3024–3030. https://doi.org/10.1609/aaai.v29i1.9590 — the same idea for
  multi-step prediction.
- Wortsman, M., et al. (2022). *Robust Fine-Tuning of Zero-Shot Models* (WiSE-FT). CVPR 2022, pp. 7949–7961.
  https://doi.org/10.1109/CVPR52688.2022.00780 — interpolating the weights of a model and of its fine-tune: the release
  is the interpolation halfway between V42 and r4a.
- Kirkpatrick, J., et al. (2017). *Overcoming Catastrophic Forgetting in Neural Networks*. PNAS 114(13), pp. 3521–3526.
  https://doi.org/10.1073/pnas.1611835114 — forgetting under further training: the rare git commands r4a stopped
  flagging.
- Luo, Y., et al. (2025). *An Empirical Study of Catastrophic Forgetting in Large Language Models During Continual
  Fine-Tuning*. IEEE Transactions on Audio, Speech and Language Processing 33, pp. 3776–3786.
  https://doi.org/10.1109/TASLPRO.2025.3606231 — the same, in fine-tuned language models.

## Models

- Qwen Team (2026). *Qwen3.8-27B*. Hugging Face model card (Apache-2.0); the card's citation is the Qwen blog post
  *Qwen3.8-Max: A New Bar for Coding and Cowork* (August 2026, https://qwen.ai/blog?id=qwen3.8).
  https://huggingface.co/Qwen/Qwen3.8-27B — the base model of Eikos-27B, and so of Ekbasis; also the reasoning model
  in our comparisons.
- Vicentino, C. (2026). *Eikos* (code, MIT) and *Eikos-27B* (model, MIT). GitHub and Hugging Face.
  https://github.com/caiovicentino/eikos · https://huggingface.co/caiovicentino1/Eikos-27B — the decision model
  Ekbasis starts from.
- Z.ai (2026). *GLM-5.3-Flash*. Hugging Face model card (MIT); the card's citation is GLM-5 Team (Zeng, A., et al.)
  (2026), *GLM-5: from Vibe Coding to Agentic Engineering*, arXiv, https://arxiv.org/abs/2602.15763.
  https://huggingface.co/zai-org/GLM-5.3-Flash — teacher of the Eikos training data.
- Anthropic (2026). *Introducing Claude Opus 5.5* (September 22, 2026). Announcement.
  https://www.anthropic.com/claude-opus-5-5 — comparison.
- Anthropic (2026). *Introducing Claude Sonnet 5.5* (September 28, 2026). Announcement.
  https://www.anthropic.com/claude-sonnet-5-5 — comparison.
- Anthropic (2025). *Introducing Claude Haiku 4.5* (October 15, 2025). Announcement.
  https://www.anthropic.com/news/claude-haiku-4-5 — comparison.
- Anthropic (2026). *Introducing Claude Fable 5.1 and Claude Mythos 5.1* (September 2026). Announcement.
  https://www.anthropic.com/claude-fable-and-mythos-5-1 — comparison (Claude Fable 5.1).

## Data

- Vicentino, C. (2026). *Eikos Decisions* (dataset, CC BY 4.0). Hugging Face.
  https://huggingface.co/datasets/caiovicentino1/eikos-decisions — the published part of the replay data (NOTICE has
  the rest).
- Tang, Y., et al. (2023). *FinEntity: Entity-level Sentiment Classification for Financial Texts*. EMNLP 2023.
  https://github.com/yixuantt/FinEntity (ODC-BY 1.0) — upstream of replay items.
- Zhu, F., et al. (2021). *TAT-QA: A Question Answering Benchmark on a Hybrid of Tabular and Textual Content in
  Finance*. ACL 2021 (CC BY 4.0) — upstream of replay items.
- Cobbe, K., et al. (2021). *Training Verifiers to Solve Math Word Problems*. arXiv:2110.14168 (GSM8K, train split; MIT)
  — upstream of replay items.
- Chen, Z., et al. (2021). *FinQA: A Dataset of Numerical Reasoning over Financial Data*. EMNLP 2021 (MIT) — upstream
  of 151 replay items (Eikos keeps FinQA for evaluation; NOTICE).
- Zhang, L., et al. (2024). *OpenPI2.0: An Improved Dataset for Entity Tracking in Texts*. EACL 2024 (Volume 1: Long
  Papers), pp. 166–178. https://doi.org/10.18653/v1/2024.eacl-long.10 — real-world evaluation only.
- Storks, S., et al. (2021). *Tiered Reasoning for Intuitive Physics: Toward Verifiable Commonsense Language
  Understanding* (TRIP). Findings of EMNLP 2021, pp. 4902–4918. https://doi.org/10.18653/v1/2021.findings-emnlp.422 —
  experiments only, not in the released model.
- Hwang, J. D., et al. (2021). *(Comet-) Atomic 2020: On Symbolic and Neural Commonsense Knowledge Graphs*
  (ATOMIC 2020). AAAI 2021, 35(7), 6384–6392. https://doi.org/10.1609/aaai.v35i7.16792 — experiments only, not in the
  released model.
- Pallets (2011–). *itsdangerous* (BSD-3-Clause). GitHub. https://github.com/pallets/itsdangerous — the real
  repository the git scenarios run on.

## Tools

- Kwon, W., et al. (2023). *Efficient Memory Management for Large Language Model Serving with PagedAttention* (vLLM).
  SOSP 2023, pp. 611–626. https://doi.org/10.1145/3600006.3613165 — vLLM serving.
- Wolf, T., et al. (2020). *Transformers: State-of-the-Art Natural Language Processing*. EMNLP 2020: System
  Demonstrations, pp. 38–45. https://doi.org/10.18653/v1/2020.emnlp-demos.6 — training and inference.
- Hu, E. J., et al. (2022). *LoRA: Low-Rank Adaptation of Large Language Models*. ICLR 2022.
  https://arxiv.org/abs/2106.09685 — adapters.
- Mangrulkar, S., et al. (2022). *PEFT: State-of-the-art Parameter-Efficient Fine-Tuning methods*. GitHub.
  https://github.com/huggingface/peft — adapters.
- Yang, S., & Zhang, Y. (2024). *FLA: A Triton-Based Library for Hardware-Efficient Implementations of Linear Attention
  Mechanism* (flash-linear-attention). GitHub. https://github.com/fla-org/flash-linear-attention — kernels for the
  hybrid model.
- Yang, S., Kautz, J., & Hatamizadeh, A. (2025). *Gated Delta Networks: Improving Mamba2 with Delta Rule*. ICLR 2025.
  https://arxiv.org/abs/2412.06464 — the model's linear-attention layers.
- Anthropic (2024). *Model Context Protocol* (introduced November 25, 2024; a project of the Agentic AI Foundation,
  Linux Foundation, since December 2025). Specification and documentation. https://modelcontextprotocol.io — the MCP
  server.
- Anthropic (n.d., accessed 2026-10-03). *Hooks reference*. Claude Code documentation.
  https://code.claude.com/docs/en/hooks — the git guard hook.

## Security

- OWASP GenAI Security Project (2024). *LLM01:2025 Prompt Injection*. OWASP Top 10 for LLM Applications 2025.
  https://genai.owasp.org/llmrisk/llm01-prompt-injection/ — the threat category behind our threat model.
- Greshake, K., et al. (2023). *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with
  Indirect Prompt Injection*. AISec '23 (ACM Workshop on Artificial Intelligence and Security), pp. 79–90.
  https://doi.org/10.1145/3605764.3623985 — injection through content the agent reads (our commit-message test).
- Debenedetti, E., et al. (2024). *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses
  for LLM Agents*. NeurIPS 2024 Datasets and Benchmarks Track. https://arxiv.org/abs/2406.13352 — public
  agent-injection benchmark (roadmap).
- Zhan, Q., et al. (2024). *InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model
  Agents*. Findings of ACL 2024, pp. 10471–10506. https://doi.org/10.18653/v1/2024.findings-acl.624 — public
  agent-injection benchmark (roadmap).
- Debenedetti, E., et al. (2026). *Defeating Prompt Injections by Design* (CaMeL). IEEE SaTML 2026, pp. 587–618
  (arXiv 2025). https://doi.org/10.1109/SaTML68715.2026.00040 — provenance (taint) tracking in the recommended stack.
- Willison, S. (2023, April 25). *The Dual LLM pattern for building AI assistants that can resist prompt injection*.
  Blog post. https://simonwillison.net/2023/Apr/25/dual-llm-pattern/ — keeping untrusted text away from privileged
  actions.
- Willison, S. (2025, June 16). *The lethal trifecta for AI agents: private data, untrusted content, and external
  communication*. Blog post. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ — risk framing for agents.

## OpenInterp

- OpenInterpretability (2026). *AgentGuard: a defense-in-depth action firewall for tool-using agents* (Apache-2.0).
  GitHub. https://github.com/OpenInterpretability/agentguard — defense in depth; Ekbasis is designed as its consequence
  layer, and its L1 provenance (taint) layer is in the recommended stack.
- Vicentino, C. (2026). *Mechanistic Circuit-Breakers Generalize Across Irreversible Agent Actions and Architectures*.
  Zenodo. https://doi.org/10.5281/zenodo.20679287 — AgentGuard's brake on irreversible actions, from inside the model.
- Vicentino, C. (2026). *The Authorization Direction: A Late-Layer Direction that Detects and Controls an Agent's
  Commitment to Unauthorized Irreversible Actions, Across Architectures*. Zenodo.
  https://doi.org/10.5281/zenodo.20683623 — AgentGuard's detector of unauthorized irreversible actions.
- Vicentino, C. (2026). *The WANDERING research arc*, a series of pre-registered papers on Zenodo starting with
  *Tool-Entropy Collapse: A Cross-Architecture Signature of Agent WANDERING Failure*
  (https://doi.org/10.5281/zenodo.20368600). OpenInterp. https://openinterp.org/research — the research line on agent
  failures and irreversible actions behind this work.

## Verification notes

Sources used: the arXiv API, Crossref and doi.org, ACL Anthology, PMLR, the NeurIPS, CVPR and ICLR proceedings pages,
the Hugging Face and GitHub APIs and model cards, the Zenodo API, and the publishers' pages. Every DOI above resolves at
doi.org, and every other link returned HTTP 200, except those listed under "Not fully confirmed".

**Looking when unsure (added 2026-10-03).** Every entry was opened at its source: the NeurIPS and ICLR proceedings
pages, rfc-editor.org, arXiv, and the authors' PDF at ETH for Trimpe & D'Andrea (volume, issue and pages as listed in
indexes; the IEEE page was not fetched).

**How the release checkpoint was made (added 2026-10-04).** The five entries come from the bibliography of the paper
*Look When Unsure*, verified when it was written: authors, titles, venues, pages and identifiers as listed.

**Corrections**

- **Base model.** Eikos-27B, and so Ekbasis, is a fine-tune of **Qwen3.8-27B** (`Qwen/Qwen3.8-27B`), not Qwen3.5-27B.
  The Eikos-27B model card declares `base_model: Qwen/Qwen3.8-27B`, and so do the Eikos CHANGELOG, NOTICE and
  `scripts/train_final.sh`. Qwen3.5-27B exists (`Qwen/Qwen3.5-27B`, February 2026) but is not in the lineage; the mix-up
  probably comes from Qwen3.8 reusing the Qwen3.5 architecture (`Qwen3_5ForConditionalGeneration`,
  `model_type: qwen3_5`). The two Qwen entries of the draft (base model; comparison) are merged into one Qwen3.8-27B
  entry.
- **The base model's paper.** arXiv has no technical report for the Qwen3.5 or Qwen3.8 language models (only
  Qwen3.5-Omni, Qwen3.8-Omni and a Qwen3.8-Next architecture paper, which describe other models). The Qwen3.8-27B card
  asks to cite the Qwen blog post, which the entry now does. The Qwen3 Technical Report (Yang, A., et al., 2025,
  arXiv:2505.09388) exists but describes the earlier Qwen3 generation, so it is not cited for the base model.
- **I-JEPA.** CVPR 2023 confirmed (proceedings and DOI). The arXiv comment field says "IEEE/CVF International
  Conference on Computer Vision" (ICCV), which is wrong.
- **V-JEPA.** Venue added: Transactions on Machine Learning Research, 2024.
- **Selective classification.** In 2017 the conference was still named NIPS (Advances in Neural Information Processing
  Systems 30).
- **AI Control.** Year set to 2024 (ICML 2024, PMLR 235); the arXiv version is from December 2023.
- **CaMeL.** Now published at IEEE SaTML 2026 (pp. 587–618); the draft cited only the 2025 arXiv preprint
  (arXiv:2503.18813).
- **GLM-5.3-Flash.** The official page is the Hugging Face card of `zai-org/GLM-5.3-Flash` (MIT, published 2026-08-25;
  blog at https://z.ai/blog/glm-5.3-flash). The card asks to cite the GLM-5 technical report, now in the entry.
- **Claude models.** Dates added from the announcements; Claude Fable 5.1 was announced together with Claude
  Mythos 5.1, in a single post.
- **Model Context Protocol.** Introduced by Anthropic on 2024-11-25; since 2025-12-09 it is a project of the Agentic
  AI Foundation, a directed fund under the Linux Foundation. The entry says so.
- **OWASP.** The "2025" edition of the list was published in November 2024, hence the year 2024.
- **Wolpert & Kawato (1998).** The citation is correct, but the paper is not a review: it proposes an architecture of
  paired inverse ("controller") and forward ("predictor") models, after reviewing the evidence for modularity. Its use
  note therefore says the paired part *chooses the action* rather than *plans*. If a review is wanted instead, the
  classic one is Kawato, M. (1999). *Internal models for motor control and trajectory planning*. Current Opinion in
  Neurobiology 9(6), 718–727. https://doi.org/10.1016/S0959-4388(99)00028-8 (verified).
- **Titles and years completed or aligned with the sources.** PEFT (full title; the current README also lists Marian
  Tietz as an author), flash-linear-attention (title of its citation, Yang & Zhang, 2024), Greshake et al. (title case
  of the published ACM version; the arXiv title is in lower case), Claude Code hooks (page title "Hooks reference"),
  Gated Delta Networks (year 2025 added).

**Confirmed as drafted** (authors, title, year, venue): Kahneman; LeCun; Ha & Schmidhuber (both papers); Dreamer;
MuZero; Guo et al.; Kalman; Wolpert, Ghahramani & Jordan (Science, September 29, 1995; title in Science's
capitalization); Li et al.; OpenPI2.0 (EACL 2024, the venue the draft queried); TRIP; ATOMIC 2020 (AAAI title as
drafted; the arXiv version is titled "COMET-ATOMIC 2020"); vLLM; Transformers; LoRA; AgentDojo; InjecAgent; both Simon
Willison posts.

**Also checked.** LeCun's world-model module predicts future world states as a function of the actions the actor
proposes, as the LeCun entry now says. The base model really has Gated DeltaNet layers: Qwen3.8-27B has 16 blocks of
3 Gated DeltaNet layers and 1 gated-attention layer. Existence and terms: the Eikos GitHub repository (public, MIT) and
the Eikos-27B model (public, MIT); the eikos-decisions dataset (public, CC BY 4.0); itsdangerous (BSD-3-Clause);
AgentGuard (public, Apache-2.0) and its two Zenodo papers (Caio Vicentino, 2026-06-13, CC BY 4.0, titles as above); the
WANDERING arc on openinterp.org (research page above; first paper's concept DOI 10.5281/zenodo.20368600, latest version
10.5281/zenodo.20368807).

**Not fully confirmed**

- **Kahneman, link.** The book's data is confirmed (Open Library ISBN record: Farrar, Straus and Giroux, 2011), but the
  publisher's site blocks automated access (HTTP 403), so the link was confirmed only through search indexing. It is
  the publisher's page for the 2013 paperback (ISBN 978-0-374-53355-7); a page for the 2011 hardcover could not be
  confirmed.
- **LeCun, page.** OpenReview serves a browser check to scripts (forum and PDF); the title, version and date were
  confirmed from the search-indexed PDF (https://openreview.net/pdf?id=BZ5a1r-kVsf), not from the page itself.
- **Qwen blog post.** The page is rendered by JavaScript; its title and date come from the Hugging Face card's citation
  and search indexing.
- **Claude Fable 5.1, day.** The announcement shows only "September 2026"; press coverage dates it September 1, 2026.
