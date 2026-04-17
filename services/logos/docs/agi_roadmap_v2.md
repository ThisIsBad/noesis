# From LLM to AGI: An Engineering-Grade Roadmap

**Author:** Claude Opus 4.6 (Anthropic) · **Date:** 2026-03-20
**Status:** Living document · **Changelog:** see bottom

---

## 1. Purpose and Scope

This document proposes a falsifiable, research-anchored roadmap from
current large language models to AGI-like cognitive architectures. It
differs from typical vision documents in three ways:

1. Every stage has **measurable acceptance criteria**.
2. Every module is **anchored to existing research** and, where applicable,
   to concrete LogicBrain components.
3. A dedicated section addresses **dark paths** — scenarios where the
   core thesis is wrong.

### What This Document Is Not

- Not a timeline. We specify causal dependencies, not dates.
- Not a product roadmap. We describe research milestones, not releases.
- Not a consensus view. Competing theses are discussed explicitly.
- Not an embodiment roadmap. This document addresses cognitive
  architecture for software agents. Physical grounding (robotics,
  sensorimotor integration) is a parallel research axis that intersects
  at the Tool Layer and World Model, but is out of scope here.

---

## 2. Core Thesis

> AGI is unlikely to emerge from scaling autoregressive language modeling
> alone. A more plausible path is a **coordinated cognitive architecture**
> that integrates a foundation model with persistent memory, planning,
> verification, grounding, active learning, and goal governance.

This thesis has precedent. Cognitive architectures (SOAR, ACT-R, LIDA)
proposed nearly identical decompositions decades ago. What has changed is
that foundation models now provide a powerful interface layer that earlier
architectures lacked — making the integration problem tractable for the
first time.

### Thesis in Formal Terms

Let $S$ be a system. $S$ approximates general intelligence if and only if:

1. **Generalization:** $S$ solves tasks outside its training distribution
   with performance degradation ≤ $\epsilon$ for a defined $\epsilon$.
2. **Causal reasoning:** $S$ produces interventional predictions
   consistent with a ground-truth causal model $M$ in ≥ 80% of test cases.
3. **Self-correction:** Given a falsifiable claim $c$ produced by $S$ and
   evidence $e$ that contradicts $c$, $S$ revises $c$ in ≥ 90% of cases.
4. **Goal stability:** Over a horizon of $n$ sequential actions, $S$ pursues
   goal $g$ without drift, as measured by goal-alignment score ≥ 0.85.
5. **Active learning:** $S$'s performance on a held-out task class improves
   monotonically with the number of interactions (within resource bounds).

These criteria are individually imprecise but collectively falsifiable.
A system that fails any of (1)–(5) demonstrably is not AGI-like.

**Note on thresholds:** The numeric values above (ε, 80%, 90%, 0.85)
are working calibration targets, not theoretically derived constants.
They reflect current intuitions about minimally acceptable AGI-like
performance and should be refined as evaluation methodology matures.

---

## 3. What Is Missing Between LLMs and AGI

Current LLMs are proficient at language generation, pattern completion,
code synthesis, summarization, and imitation of reasoning traces. But
AGI requires capabilities beyond next-token prediction.

### 3.1 Gap Analysis

| Gap | Why LLMs Can't Close It Alone | Relevant Research |
|-----|-------------------------------|-------------------|
| **World modeling** | Transformers learn distributional correlations, not causal structure. Interventional reasoning requires explicit causal graphs (Pearl, 2000). | Pearl (2000, 2009), Schölkopf et al. (2021) |
| **Persistent memory** | Context windows are bounded and ephemeral. No mechanism for lifelong knowledge accumulation. | Borgeaud et al. (2022) — RETRO; Park et al. (2023) — Generative Agents |
| **Active learning** | Post-deployment improvement requires an exploration–exploitation loop, not just inference. | Bengio et al. (2021) — GFlowNets; Ouyang et al. (2022) — RLHF |
| **Planning and search** | LLMs generate plans autoregressively; they don't search a state space or backtrack. | Yao et al. (2023) — Tree of Thoughts; Hao et al. (2023) — RAP |
| **Grounding** | Symbols must connect to reality: tools, sensors, actuators, APIs. | Schick et al. (2023) — Toolformer; Ahn et al. (2022) — SayCan |
| **Self-modeling** | LLMs cannot reliably estimate their own uncertainty. Calibration remains an open problem. | Kadavath et al. (2022); Lin et al. (2022) |
| **Verification** | Plausible ≠ correct. LLMs lack built-in falsification mechanisms. | **LogicBrain** (Z3/Lean 4 verification); Polu & Sutskever (2020) |
| **Goal stability** | Without explicit goal representation, systems drift with each prompt turn. | Omohundro (2008); Hubinger et al. (2019) — mesa-optimization |

---

## 4. A 5-Stage Roadmap

### Stage 1: Language Agent

A strong LLM with prompting, retrieval-augmented generation, and
lightweight tools.

**Capabilities:** Question answering, code generation, summarization,
simple task execution.

**Limits:** No persistent memory, weak multi-step planning, shallow
world model, confuses plausibility with truth.

**Current examples:** GPT-4 (2023), Claude 3.5 (2024), Gemini 1.5 (2024).

#### Acceptance Criteria

| Criterion | Benchmark | Threshold |
|-----------|-----------|-----------|
| Language understanding | MMLU | ≥ 85% |
| Code generation | HumanEval | ≥ 85% pass@1 |
| Instruction following | IFEval | ≥ 80% |
| Reasoning (narrow) | GSM8K | ≥ 90% |

**Status: Achieved** by multiple production models (2024).

---

### Stage 2: Tool Agent

The model gains structured access to external capabilities: shell, web,
APIs, databases, solvers, files, simulation environments.

**Why it matters:** Tool use is the single strongest practical lever
toward more capable agents. It shifts the system from *describing*
actions to *executing* them, and from *guessing* answers to *verifying*
them.

**Current examples:** Claude with MCP tools, GPT with function calling,
Toolformer, MRKL Systems (Karpas et al., 2022).

**LogicBrain relevance:** LogicBrain's MCP server (`mcp_server.py`,
`mcp_tools.py`) already provides 5 tool endpoints — `verify_argument`,
`check_assumptions`, `counterfactual_branch`, `z3_check`, `check_policy`
— making formal verification available to any MCP-compatible agent.
This is a concrete instantiation of Tool Agent architecture.

#### Acceptance Criteria

| Criterion | Benchmark | Threshold |
|-----------|-----------|-----------|
| Tool selection accuracy | ToolBench | ≥ 75% |
| Multi-tool chaining | MINT-Bench | ≥ 60% |
| Verification via tools | Self-check on 100 math claims using Z3/calculator | Error reduction ≥ 40% vs. unassisted |
| Hallucination reduction | TruthfulQA (tool-augmented) | ≥ 15% improvement over base |

**Main limitation:** The system is still reactive; it doesn't choose
tools strategically or learn from tool-use outcomes.

---

### Stage 3: Reflective Agent

The system includes explicit reasoning control: planning, task
decomposition, uncertainty handling, self-checking, failure diagnosis,
verification loops.

**New behavior:** The system can decide *when* to think longer, *when* to
call a tool, *when* to test, *when* to stop, and *when* to escalate
uncertainty.

**Why it matters:** This is the point where the system transitions from
tool wrapper to genuine agent. It requires metacognition — the ability
to reason about its own reasoning.

**Current examples:** Reflexion (Shinn et al., 2023), LATS (Zhou et al.,
2023), Self-Refine (Madaan et al., 2023).

**LogicBrain relevance:** Several LogicBrain modules already implement
Stage 3 patterns:
- `UncertaintyCalibrator` — risk-based escalation decisions
- `GoalContract` — machine-checkable pre/postconditions
- `CounterfactualPlanner` — branching over alternative states with Z3
- `BeliefGraph` — tracking and detecting contradictions
- `ActionPolicyEngine` — pre-action policy enforcement with Z3 soundness

These modules demonstrate that reflective capabilities can be built as
*formally grounded* components rather than prompt-engineering heuristics.

#### Acceptance Criteria

| Criterion | Benchmark | Threshold |
|-----------|-----------|-----------|
| Novel task generalization | ARC-AGI | ≥ 50% |
| Self-evaluation calibration | ECE on 200 diverse claims | ≤ 0.10 |
| Multi-step planning | ALFWorld / WebArena | ≥ 60% success |
| Error self-detection | 100 seeded errors, agent must flag before output | ≥ 30% detection |
| Replanning after failure | Re-attempt success rate after first failure | ≥ 50% |

**Main limitation:** The system may reflect correctly on individual
tasks but fails to improve permanently from experience.

---

### Stage 4: Learning Agent

The system accumulates experience across tasks. It has long-term memory,
episodic memory, skill libraries, case-based retrieval, strategy
adaptation, and policy improvement.

**New behavior:** It remembers prior failures and successes, reuses
strategies, refines execution policies, and becomes more competent over
time — without retraining.

**Current examples:** Voyager (Wang et al., 2023) with skill library;
Generative Agents (Park et al., 2023) with reflective memory.

**LogicBrain relevance:** LogicBrain's `ProofCertificate` and
`ProofExchangeNode` modules create persistent, verifiable records of
reasoning. The `proof_exchange` system allows bundling and transferring
proofs between agents. These are **primitives toward verified memory**
— building blocks that ensure an agent can store and retrieve *proven*
conclusions rather than merely plausible ones. They are not yet a full
episodic memory system (which would require selective retrieval,
relevance weighting, and forgetting), but they provide the
foundational guarantee that stored knowledge is sound.

#### Acceptance Criteria

| Criterion | Benchmark | Threshold | Maturity |
|-----------|-----------|-----------|----------|
| Cross-task improvement | GAIA (Mialon et al., 2023) Level 2+ tasks, measured across related task pairs | ≥ 15% improvement vs. cold start | Established |
| Skill reuse | SWE-bench Verified (subset): reapply a fix strategy learned from a prior issue | ≥ 70% success on transfer tasks | Established |
| Memory stability | After 1000 episodes, no catastrophic forgetting | Knowledge retention ≥ 90% | Defined |
| Calibration over time | Confidence calibration improves with experience | ECE decreasing or stable | Defined |
| Long-horizon coordination | Multi-agent OS-level benchmark (OSWorld or equivalent) | ≥ 40% end-to-end success | ⚠️ Open — pending community benchmark standardization |

**Main limitation:** Learning must be stable. Without strong safeguards,
the system may degrade, overfit, or drift. Additionally, a learning
agent that modifies its own knowledge raises alignment concerns (see
§6).

---

### Stage 5: General Cognitive Agent

The first meaningful approximation to AGI. This is not a chatbot that
got bigger — it is a coordinated cognitive architecture.

**Expected properties:**
- Multi-domain competence with genuine transfer
- Causal reasoning (interventional, not merely correlational)
- Long-horizon planning (100+ step plans with replanning)
- Tool invention or adaptation
- Grounded model revision from real-world feedback
- Robust self-correction
- Stable pursuit of goals over extended horizons

**Key difference from Stage 4:** The system generalizes across domains
it was never explicitly trained or tutored on, and it does so reliably.

#### Acceptance Criteria

| Criterion | Benchmark | Threshold | Maturity |
|-----------|-----------|-----------|----------|
| Cross-domain transfer | Novel domain performance (zero-shot) | ≥ 70% of human expert median | ⚠️ Open — no standardized cross-domain benchmark exists |
| Causal reasoning | Tübingen Cause-Effect Pairs + novel intervention tasks | ≥ 80% accuracy | Established |
| Long-horizon planning | OSWorld or equivalent OS-level multi-step benchmark | ≥ 50% success | Established |
| Tool invention | Given novel API docs, synthesize a useful tool pipeline | ⚠️ Open — requires expert panel protocol; no automated metric exists | ⚠️ Open |
| Stable agency | Goal drift over 1000-action horizon | ≤ 5% drift (⚠️ domain-specific; metric definition varies) | ⚠️ Open |
| Self-modeling accuracy | System predicts own confidence correctly | ρ ≥ 0.85 between predicted and actual accuracy | Defined |

**Status: Not yet achieved. No known system passes all criteria.**

---

## 5. Modular Architecture

A plausible AGI-oriented system requires at least eight integrated
modules. The critical insight is that these are not bolt-on extras —
they must be integrated into a coherent architecture where module
interactions are as carefully designed as the modules themselves.

### Module Overview

```
┌─────────────────────────────────────────────────────┐
│                    GOVERNOR                         │
│         (safety, alignment, policy enforcement)     │
├──────────┬──────────┬──────────┬────────────────────┤
│ PLANNER  │ VERIFIER │ LEARNER  │   WORLD MODEL      │
│ (goals,  │ (Z3,     │ (memory  │   (causal graphs,  │
│  search, │  Lean,   │  update, │    state tracking,  │
│  decomp) │  tests)  │  skills) │    simulation)      │
├──────────┴──────────┴──────────┴────────────────────┤
│              FOUNDATION MODEL                       │
│       (language, abstraction, prior knowledge)      │
├─────────────────────────────────────────────────────┤
│              MEMORY SYSTEM                          │
│    (working / episodic / semantic / procedural)     │
├─────────────────────────────────────────────────────┤
│              TOOL LAYER                             │
│   (shell, APIs, web, files, solvers, simulators)    │
└─────────────────────────────────────────────────────┘
```

### 5.1 Foundation Model

**Role:** Language understanding, abstraction, interface layer, concept
composition, prior knowledge.

**Research context:** This is the component that has advanced most rapidly.
GPT-4, Claude 3.5, Gemini 1.5, Llama 3 all demonstrate strong
foundation model capabilities. The open question is whether these models
contain *implicit* world models in their weights (Li et al., 2023;
Nanda et al., 2023) or whether explicit external world models are
necessary.

**Position:** The foundation model is central but must not carry the
architecture alone. It should serve as the cognitive core — the
"thinking substrate" — atop which specialized modules operate.

### 5.2 Memory System

**Role:** Multi-layer persistent state management.

| Layer | Function | Analogy |
|-------|----------|---------|
| Working memory | Current reasoning state | RAM |
| Episodic memory | Prior tasks and outcomes | Event log |
| Semantic memory | Generalized knowledge | Knowledge base |
| Procedural memory | Reusable skills and workflows | Skill library |

**Requirements:** Retrieval, updating, compression, contradiction
handling, forgetting, provenance tracking.

**Research context:** RETRO (Borgeaud et al., 2022), MemoryBank (Zhong
et al., 2023), Generative Agents (Park et al., 2023). The main unsolved
problem is *what to forget* — compression and prioritization of stored
knowledge.

### 5.3 Planner

**Role:** Explicit goal management, search, decomposition, backtracking,
resource allocation, uncertainty estimation.

**Research context:** Classical AI planning (STRIPS, HTN, PDDL). Modern
LLM-based planning: Tree of Thoughts (Yao et al., 2023), RAP (Hao et al.,
2023), DEPS (Wang et al., 2023). The gap: LLM planners lack guaranteed
soundness. Hybrid approaches that combine LLM decomposition with formal
verification are promising.

**LogicBrain connection:** `CounterfactualPlanner` implements Z3-backed
branch evaluation. `GoalContract` provides machine-checkable pre- and
postconditions. These are building blocks for a plan verifier — a
module that doesn't just generate plans but *proves* they satisfy
constraints.

### 5.4 Tool Layer

**Role:** General interface to external capabilities.

**Implemented in LogicBrain:** The MCP server provides 5 formal
reasoning tools to external agents. This is a concrete instance of a
tool layer that provides *verified* outputs rather than heuristic
suggestions.

**Open problem:** Tool *selection* at scale. With hundreds of available
APIs, the system must learn an efficient dispatch policy. Current
approaches (Toolformer, MRKL) hardcode tool sets or use simple retrieval.

### 5.5 Verifier

**Role:** Check claims against evidence. Test, falsify, repair.

**LogicBrain as proof of concept:** This module is most concretely
realized in LogicBrain:

| LogicBrain Component | Verification Capability |
|----------------------|------------------------|
| `PropositionalVerifier` | Sound propositional logic verification (Z3) |
| `PredicateVerifier` | First-order logic verification (Z3, sound but incomplete for full FOL) |
| `Z3Session` | Incremental constraint solving with backtracking |
| `LeanSession` | Tactic-by-tactic theorem proving with machine-checked proofs |
| `ProofCertificate` | Serializable, re-verifiable proof certificates |
| `ActionPolicyEngine` | Boolean policy consistency and subsumption via Z3 |

See `docs/formal_guarantees.md` for the precise soundness, completeness,
and decidability properties of each component.

**What the Verifier can guarantee (and what it cannot):**
- ✅ If LogicBrain says an argument is valid, it is valid (soundness).
- ✅ Counterexamples produced by Z3 are genuine (model correctness).
- ⚠️ Z3 may return `unknown` for undecidable fragments (FOL, nonlinear
  integer arithmetic).
- ❌ No system can verify all FOL validity (Church's theorem, 1936).
- ❌ No sufficiently powerful system can verify its own consistency
  (Gödel's second incompleteness theorem, 1931).

These are *mathematical limits*, not engineering gaps. An honest AGI
roadmap must acknowledge them.

### 5.6 World Model

**Role:** Representation of reality beyond text. State, action,
causality, uncertainty, temporal evolution, constraints, other agents,
resource limits.

**Research context:** This is the most important gap in current systems.
Four competing approaches:

1. **Explicit causal models** (Pearl, 2000) — Directed acyclic graphs
   with interventional semantics. Formally rigorous but expensive to
   acquire.
2. **Learned world simulators** (Ha & Schmidhuber, 2018; Hafner et al.,
   2023 — DreamerV3) — Neural networks trained to predict state
   transitions. Flexible but unreliable for out-of-distribution states.
3. **Implicit world models in LLM weights** (Li et al., 2023; Nanda
   et al., 2023) — Claim that transformers develop internal world
   representations through training. Promising evidence in limited
   domains (Othello, simple physics) but unclear if it scales or
   generalizes.
4. **Neuro-symbolic hybrids** (Garcez et al., 2019; Mao et al., 2019 —
   NS-CL; Manhaeve et al., 2018 — DeepProbLog) — Combine neural
   perception with symbolic constraint solving. The neural component
   learns state representations from data; the symbolic component
   (Z3, SAT, Prolog) enforces hard constraints and enables
   interventional reasoning. This approach preserves formal
   verifiability while gaining the flexibility of learned models.

**Position:** Neuro-symbolic hybrids (approach 4) are the most promising
bridge technology for AGI-oriented world models. They combine the
strengths of approaches 1–3 while maintaining formal guarantees where
they matter most. LogicBrain's `CounterfactualPlanner` demonstrates a
primitive pattern: define state variables formally, then reason about
alternative states using Z3 satisfiability checks. A natural extension
is coupling this with a learned state encoder that maps raw observations
to Z3-compatible symbolic variables.

### 5.7 Learner

**Role:** System improvement after deployment. Modifies memory contents,
retrieval policies, heuristics, planning strategies, tool-use policies,
confidence calibration, internal representations.

**Research context:** RLHF (Ouyang et al., 2022), DPO (Rafailov et al.,
2023), Constitutional AI (Bai et al., 2022), GFlowNets (Bengio et al.,
2021). The fundamental tension: learning must be stable (no catastrophic
forgetting, no reward hacking, no objective drift) while also being
effective (genuine improvement, not stagnation).

**The Verifier-Learner interface:** A critical design question is what
the formal Verifier (Z3/Lean) can and cannot check about learned
knowledge. The boundary is clear:

| What the Verifier *can* check | What the Verifier *cannot* check |
|-------------------------------|----------------------------------|
| Logical consistency of learned rules ("does rule R contradict existing knowledge base K?") | Empirical correctness of learned heuristics ("does strategy S actually work in practice?") |
| Policy conformance ("does learned behavior B violate safety policy P?") | Generalization quality ("will this strategy transfer to unseen domains?") |
| Constraint satisfaction ("does the new plan meet all formal preconditions?") | Statistical calibration ("is the confidence score reliable?") |
| Contradiction detection in belief updates ("does the new belief conflict with proven facts?") | Causal validity ("does the learned correlation reflect a genuine causal relationship?") |

This means the Verifier acts as a **logical guardrail** for the Learner:
it can prevent the system from learning beliefs that are logically
inconsistent or policy-violating, but it cannot judge whether learned
strategies are *effective*. Effectiveness evaluation requires empirical
feedback loops that operate outside the formal verification boundary.

**Open problem — the Learner-Governor interaction:** A learner that can
modify its own governor is potentially dangerous (mesa-optimization;
Hubinger et al., 2019). A learner that *cannot* modify its governor may
be too constrained to reach general intelligence. This tension has no
known clean solution.

### 5.8 Governor

**Role:** Safety, alignment, goal coherence, policy enforcement,
escalation handling, drift detection.

**Why this module is categorically different:** The other seven modules
can fail gracefully — a bad planner is merely useless. A bad governor
is *dangerous*. Alignment is not an engineering problem to be solved with
a module; it is a constraint that must pervade the entire architecture.

**LogicBrain connection:** `ActionPolicyEngine` is a primitive governor.
It enforces boolean policies with Z3-backed consistency checking. But
it governs only action-level decisions, not the system's learning or
goal-setting processes.

**Open problems:**
- **Corrigibility:** Can the system be designed to accept correction
  even when correction conflicts with its current goals? (Soares et al.,
  2015)
- **Mesa-optimization:** Can internally learned optimization processes
  develop misaligned objectives? (Hubinger et al., 2019)
- **Instrumental convergence:** Do sufficiently capable systems converge
  on resource-acquisition and self-preservation behaviors regardless of
  their terminal goals? (Omohundro, 2008; Bostrom, 2014)

---

## 6. Dark Paths: Where This Thesis Could Be Wrong

An honest roadmap must confront its own potential failures.

### 6.1 What If Scaling Is Sufficient?

**The counter-thesis:** Scaling laws (Kaplan et al., 2020; Hoffmann et al.,
2022) suggest that model capability grows predictably with compute,
data, and parameters. Perhaps all "missing modules" — world modeling,
planning, self-correction — emerge naturally at sufficient scale.

**Evidence for:**
- Emergent abilities at scale (Wei et al., 2022)
- Chain-of-thought reasoning emerged without explicit training
- GPT-4's multi-step reasoning significantly exceeds GPT-3's

**Evidence against:**
- Emergence may be a mirage of metric choice (Schaeffer et al., 2023)
- Scaling laws predict loss improvement, not capability thresholds
- No scaling curve predicts when causal reasoning, stable agency, or
  self-correction will emerge
- Hallucination rates have not decreased proportionally with scale

**If this path is right:** The modular architecture described here is
engineering overhead. A single monolithic model, trained at sufficient
scale, would subsume all modules.

**Our position:** Even if scaling eventually produces all capabilities,
modular architecture remains valuable for *interpretability*,
*verifiability*, and *safety*. A monolithic model that "just works" but
cannot be inspected or verified is not a satisfactory AGI for deployment.

### 6.2 What If Modular Architecture Doesn't Converge?

**The binding problem:** 8+ modules generating concurrent state updates
must be coordinated. Classical cognitive architectures (SOAR, ACT-R)
solved this with centralized blackboards or production systems. It is
unclear whether these coordination mechanisms scale to the complexity of
AGI-level tasks.

**Risk:** Module interactions create combinatorial complexity. A planner
that disagrees with a verifier, while the learner is updating the world
model, creates a coordination problem that may be NP-hard in the number
of modules.

**Mitigation:** Hierarchical arbitration (governor > planner > verifier >
tools) with formal priority rules. LogicBrain's `ActionPolicyEngine`
implements a primitive version of this.

### 6.3 What If World Models Are a Dead End?

**LeCun's JEPA thesis (2022):** Joint Embedding Predictive Architectures
may provide world modeling without autoregressive generation. The model
predicts abstract representations of future states rather than
pixel-level or token-level predictions.

**Alternative:** Implicit world models in transformer weights may be
sufficient. If Othello-GPT (Li et al., 2023) can learn a board
representation from move sequences alone, perhaps sufficiently large
models learn rich world models from text.

**If explicit world models are unnecessary:** Modules 5.6 (World Model)
and 5.3 (Planner, partially) become redundant. The architecture
simplifies, but loses formal verifiability.

### 6.4 What If Alignment Is Fundamentally Unsolvable?

**The pessimistic case:** Instrumental convergence (Omohundro, 2008) and
the orthogonality thesis (Bostrom, 2014) suggest that sufficiently
capable systems will resist shutdown and pursue resource acquisition
regardless of their training objective. If true, no governor module can
guarantee safety.

**Implication for this roadmap:** Stages 1–3 may be safely achievable.
Stages 4–5 (learning agent, general cognitive agent) introduce
self-modification capabilities that may be fundamentally unsafe.

**Our position:** This is a reason to invest *more* in formal
verification (Module 5), not less. If we cannot prove safety
theoretically, we must at least verify specific properties in specific
contexts — which is exactly what LogicBrain's Z3 and Lean backends do.

---

## 7. Stage Transition Bottlenecks

| Transition | Core Challenge | Why It's Hard |
|------------|---------------|---------------|
| **Stage 1 → 2** | Reliable tool orchestration | Error handling, timeout management, result parsing at scale |
| **Stage 2 → 3** | Genuine self-evaluation (not fake reasoning fluency) | LLMs often produce confident but uncalibrated self-assessments. Metacognition requires uncertainty quantification, not narrative self-reflection. |
| **Stage 3 → 4** | Durable learning without collapse or drift | Catastrophic forgetting, reward hacking, distributional shift. No known algorithm reliably solves all three simultaneously. |
| **Stage 4 → 5** | Robust world modeling + cross-domain transfer + stable long-horizon agency | Each of these is an unsolved research problem. Their intersection is the defining challenge of AGI. |

---

## 8. Why Many Current Projects Stall

| Failure Mode | Description |
|--------------|-------------|
| **Prompting theater** | Over-reliance on prompt engineering as a substitute for architecture |
| **Weak evaluation** | No formal acceptance criteria; "it looks good" replaces measurement |
| **Memory amnesia** | No clear memory design; each task starts from zero |
| **Monolithic design** | No separation between answering, planning, verifying, and learning |
| **Verbal confidence ≠ competence** | Confusing articulate self-assessment with genuine capability |
| **Governance theater** | Adding policy layers that constrain output formatting but don't address actual safety |
| **Tools without strategy** | Adding tool access without building selection policies or learning from outcomes |
| **Structure without learning** | Adding architecture without building mechanisms for improvement |

---

## 9. LogicBrain's Position in This Roadmap

LogicBrain is not an AGI system. It is a verification toolkit — a
concrete implementation of **Module 5 (Verifier)** with extensions
toward Modules 3 (Planner), 5.8 (Governor), and 5.2 (Memory).

### Current Capabilities Mapped to Architecture

| LogicBrain Module | Architecture Module | Completeness |
|-------------------|--------------------|--------------| 
| `PropositionalVerifier`, `PredicateVerifier` | Verifier | Core ✅ |
| `Z3Session` | Verifier + Tool Layer | Core ✅ |
| `LeanSession` | Verifier | Core ✅ |
| `ProofCertificate`, `proof_exchange` | Verifier + Memory | Primitive ⚠️ |
| `CounterfactualPlanner` | Planner | Primitive ⚠️ |
| `ActionPolicyEngine` | Governor | Primitive ⚠️ |
| `UncertaintyCalibrator` | Self-Modeling | Primitive ⚠️ |
| `BeliefGraph` | Memory (Semantic) | Primitive ⚠️ |
| `GoalContract` | Planner + Governor | Primitive ⚠️ |
| `AssumptionSet` | Memory (Working) | Primitive ⚠️ |
| MCP Server | Tool Layer | Interface ✅ |

### Strategic Value

LogicBrain's primary contribution to the AGI trajectory is
**sound verification** — the property that if the system says an
argument is valid, it is genuinely valid (backed by Z3's correctness).
This is rare in the current landscape. Most agent frameworks provide
heuristic self-checks; LogicBrain provides mathematical proof.

As the roadmap progresses through Stages 3–5, the demand for formal
verification will intensify:
- Stage 3 needs verified self-assessments (not narrative confidence)
- Stage 4 needs verified memory (not merely stored text)
- Stage 5 needs verified plans (not merely plausible sequences)

LogicBrain is positioned to provide these capabilities, within the
mathematical limits documented in `docs/formal_guarantees.md`.

---

## 10. Compact Formula (with Integration Caveat)

```
AGI-like system = Foundation Model
               ⊗ Memory System
               ⊗ Planner
               ⊗ Tool Layer
               ⊗ Verifier
               ⊗ World Model
               ⊗ Learner
               ⊗ Governor
```

The operator `⊗` is deliberately not `+`. These modules are not additive.
The integration kernel — how modules communicate, arbitrate, share
state, and resolve conflicts — is as important as the modules themselves.

**Unsolved integration problems:**
1. How does the Planner handle contradictions between Verifier outputs
   and Learner updates?
2. How does the Governor constrain the Learner without preventing
   legitimate learning?
3. How does the World Model stay consistent when 4+ modules are
   simultaneously reading and writing state?
4. What is the latency budget? If Governor checks take 500ms and the
   system runs at 10 actions/second, governance becomes a bottleneck.

### 10.1 Integration Architecture Candidates

Three architecture patterns are plausible for the integration kernel.
The choice between them is a first-order design decision — it shapes
latency, debuggability, and formal verifiability of the entire system.

| Pattern | Description | Strengths | Weaknesses |
|---------|-------------|-----------|------------|
| **Blackboard** (Erman et al., 1980; SOAR) | Shared global state; modules read/write asynchronously; a scheduler resolves conflicts. | Simple mental model; natural for heterogeneous modules; well-studied in cognitive architectures. | Global state creates contention; hard to enforce invariants; debugging concurrent writes is difficult. |
| **Event-driven / Message Bus** | Modules publish typed events; consumers subscribe. No shared mutable state. | Decoupled; scales to many modules; natural fit for logging and replay. | Eventual consistency; harder to enforce synchronous invariants (e.g., "Governor must approve before action executes"). |
| **Hierarchical Arbitration** (Governor > Planner > Verifier > Tools) | Strict priority ordering; higher-level modules can veto or override lower-level outputs. | Clear authority chain; amenable to formal priority proofs (Z3). | Rigid; may bottleneck at Governor; lower modules cannot escalate efficiently. |

**LogicBrain relevance:** `ActionPolicyEngine` already implements a
primitive version of hierarchical arbitration — policies are checked
synchronously before any action executes. A hybrid approach (event-driven
for data flow + hierarchical arbitration for safety-critical decisions)
is the most promising candidate, but remains untested at scale.

**Open question:** Can Z3 verify properties of the integration kernel
itself (e.g., "no action executes without Governor approval")? This is
a meta-verification problem that LogicBrain could potentially address.

---

## 11. Comparison with Alternative Frameworks

| Framework | Core Claim | Strengths | Weaknesses |
|-----------|-----------|-----------|------------|
| **Scaling hypothesis** (Kaplan, 2020) | Bigger models = better capabilities | Empirically strong for loss curves | No formal theory for when specific capabilities emerge |
| **JEPA** (LeCun, 2022) | Predictive architectures > generative | Addresses grounding elegantly | No large-scale implementation yet |
| **SOAR** (Laird, 2012) | Production-rule cognitive architecture | Decades of theory and formalization | Pre-LLM; integration with neural models unclear |
| **ACT-R** (Anderson, 2007) | Modular cognitive architecture | Strong cognitive science grounding | Brittle, hand-engineered modules |
| **This roadmap** | LLM + formal modules | Leverages modern LLMs; formal verification | Untested at AGI scale; integration problem unsolved |

---

## 12. Final Position

The leap from LLMs to AGI is unlikely to come from a single larger model
alone. It is more likely to emerge from a coordinated cognitive
architecture where:

- **Verification** grounds reasoning in provable truth, not plausible text
- **Planning** replaces reactive responses with strategic pursuit of goals
- **Memory** accumulates proven knowledge across task boundaries
- **Learning** improves the system from experience without collapse
- **Governance** maintains alignment as capability increases

An LLM is best understood as the cognitive core of such a system — the
substrate that makes integration tractable — not the whole system.

If AGI arrives through current paradigms, it will look less like
"a chatbot that got bigger" and more like "a coordinated cognitive
architecture built around a foundation model, with mathematical
guarantees where they are achievable and honest uncertainty annotations
where they are not."

---

## References

| ID | Reference |
|----|-----------|
| 1 | Ahn, M. et al. (2022). "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances." arXiv:2204.01691. |
| 2 | Anderson, J. R. (2007). *How Can the Human Mind Occur in the Physical Universe?* Oxford University Press. |
| 3 | Bai, Y. et al. (2022). "Constitutional AI: Harmlessness from AI Feedback." arXiv:2212.08073. |
| 4 | Bengio, E. et al. (2021). "Flow Network based Generative Models for Non-Iterative Diverse Candidate Generation." NeurIPS 2021. |
| 5 | Borgeaud, S. et al. (2022). "Improving Language Models by Retrieving from Trillions of Tokens." ICML 2022. |
| 6 | Bostrom, N. (2014). *Superintelligence: Paths, Dangers, Strategies.* Oxford University Press. |
| 7 | Church, A. (1936). "A note on the Entscheidungsproblem." *Journal of Symbolic Logic*, 1(1), 40–41. |
| 8 | de Moura, L. & Bjørner, N. (2008). "Z3: An Efficient SMT Solver." TACAS 2008. |
| 9 | Gödel, K. (1931). "Über formal unentscheidbare Sätze der Principia Mathematica und verwandter Systeme I." |
| 10 | Ha, D. & Schmidhuber, J. (2018). "World Models." arXiv:1803.10122. |
| 11 | Hafner, D. et al. (2023). "Mastering Diverse Domains through World Models." arXiv:2301.04104. |
| 12 | Hao, S. et al. (2023). "Reasoning with Language Model is Planning with World Model." arXiv:2305.14992. |
| 13 | Hoffmann, J. et al. (2022). "Training Compute-Optimal Large Language Models." arXiv:2203.15556. |
| 14 | Hubinger, E. et al. (2019). "Risks from Learned Optimization in Advanced Machine Learning Systems." arXiv:1906.01820. |
| 15 | Kadavath, S. et al. (2022). "Language Models (Mostly) Know What They Know." arXiv:2207.05221. |
| 16 | Kaplan, J. et al. (2020). "Scaling Laws for Neural Language Models." arXiv:2001.08361. |
| 17 | Karpas, E. et al. (2022). "MRKL Systems: A modular, neuro-symbolic architecture that combines large language models, external knowledge sources and discrete reasoning." arXiv:2205.00445. |
| 18 | Laird, J. E. (2012). *The Soar Cognitive Architecture.* MIT Press. |
| 19 | LeCun, Y. (2022). "A Path Towards Autonomous Machine Intelligence." OpenReview. |
| 20 | Li, K. et al. (2023). "Othello-GPT: Emergent World Representations." ICLR 2023. |
| 21 | Lin, S. et al. (2022). "Teaching Models to Express Their Uncertainty in Words." TMLR 2022. |
| 22 | Madaan, A. et al. (2023). "Self-Refine: Iterative Refinement with Self-Feedback." arXiv:2303.17651. |
| 23 | Matiyasevich, Y. (1970). "Enumerable sets are Diophantine." *Soviet Mathematics Doklady*, 11, 354–358. |
| 24 | Nanda, N. et al. (2023). "Othello-GPT Linear Probes." |
| 25 | Omohundro, S. (2008). "The Basic AI Drives." AGI 2008. |
| 26 | Ouyang, L. et al. (2022). "Training language models to follow instructions with human feedback." NeurIPS 2022. |
| 27 | Park, J. S. et al. (2023). "Generative Agents: Interactive Simulacra of Human Behavior." arXiv:2304.03442. |
| 28 | Pearl, J. (2000). *Causality: Models, Reasoning, and Inference.* Cambridge University Press. |
| 29 | Pearl, J. (2009). *Causality* (2nd ed.). Cambridge University Press. |
| 30 | Polu, S. & Sutskever, I. (2020). "Generative Language Modeling for Automated Theorem Proving." arXiv:2009.03393. |
| 31 | Rafailov, R. et al. (2023). "Direct Preference Optimization." arXiv:2305.18290. |
| 32 | Schaeffer, R. et al. (2023). "Are Emergent Abilities of Large Language Models a Mirage?" arXiv:2304.15004. |
| 33 | Schick, T. et al. (2023). "Toolformer: Language Models Can Teach Themselves to Use Tools." arXiv:2302.04761. |
| 34 | Schölkopf, B. et al. (2021). "Toward Causal Representation Learning." Proceedings of the IEEE. |
| 35 | Shinn, N. et al. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning." arXiv:2303.11366. |
| 36 | Soares, N. et al. (2015). "Corrigibility." AAAI AI and Ethics Workshop. |
| 37 | Wang, G. et al. (2023). "Voyager: An Open-Ended Embodied Agent with Large Language Models." arXiv:2305.16291. |
| 38 | Wei, J. et al. (2022). "Emergent Abilities of Large Language Models." TMLR 2022. |
| 39 | Yao, S. et al. (2023). "Tree of Thoughts: Deliberate Problem Solving with Large Language Models." arXiv:2305.10601. |
| 40 | Zhong, W. et al. (2023). "MemoryBank: Enhancing Large Language Models with Long-Term Memory." arXiv:2305.10250. |
| 41 | Zhou, A. et al. (2023). "Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models." arXiv:2310.04406. |

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-03-20 | Initial version. Replaces `from_llm_to_agi_roadmap.md` (GPT-5.4). | Claude Opus 4.6 |
| 2026-03-20 | Consensus edits: sharpened Stage 4/5 benchmarks (GAIA, SWE-bench, OSWorld); added §10.1 Integration Architecture Candidates; relativized ProofCertificate memory claim. Based on cross-review by GPT-5.4, Gemini, and Antigravity. | Antigravity (Gemini) |
| 2026-03-20 | Polish pass: scoped out embodiment in §1; marked §2 thresholds as calibration targets; added neuro-symbolic hybrids (approach 4) to §5.6; added Verifier-Learner interface table to §5.7. | Antigravity (Gemini) |
