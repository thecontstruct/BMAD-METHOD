# Research: Prompt Compilation & Composition Landscape

**Generated:** 2026-04-10
**Source:** Perplexity Deep Research
**Context:** Prior art research for the BMAD Compiled Skills proposal

---

## Executive Summary

The landscape of prompt composition systems is fragmented and emerging, with most solutions being either domain-specific implementations within larger frameworks or research-stage prototypes. While mature "compiled prompt" infrastructure comparable to traditional software build pipelines is limited, several projects and approaches are pioneering patterns that treat prompts as composable source code. The field lacks a dominant, standardized architecture — creating significant opportunity for novel solutions.

**No single project fully addresses** composable fragments, build-time compilation, user override safety, multi-model adaptation, and multi-agent prompt assembly together. The BMAD proposal would be the first integrated approach.

---

## 1. The Prompt Compilation Gap

The AI agent space currently suffers from a **prompt management crisis**:

- **Monolithic prompts**: Most LLM integrations hardcode prompts as strings or files, with versioning/customization managed ad-hoc
- **No build pipeline**: Unlike traditional software, prompts typically lack compilation steps, dependency management, or deterministic assembly
- **Personalization friction**: End-users struggle to customize agent behavior without deep code modification
- **Multi-model fragmentation**: Different LLM backends require prompt adjustments, forcing duplication or runtime branching logic
- **Subagent chaos**: Multi-agent systems often have agents constructing other agents' prompts dynamically — error-prone and non-deterministic

This gap exists because prompt engineering has historically been treated as a *craft* (qualitative) rather than *engineering* (systematic), and no industry standard has emerged.

---

## 2. Key Concepts

### Prompt Compilation vs. Templating

| Aspect | Simple Templating | Prompt Compilation |
|---|---|---|
| **Definition** | String interpolation/substitution | Multi-stage pipeline: parse → transform → optimize → assemble |
| **Artifacts** | Template + data → rendered string | Source fragments + config → compiled prompt with metadata |
| **State management** | Stateless (each render independent) | Stateful (dependency resolution, version tracking) |
| **Customization** | Append/override variables | Patch-based system with conflict detection |
| **Target model awareness** | Runtime if-statements | Build-time variant generation |

---

## 3. Existing Projects & Frameworks

### Open Source

#### DSPy (Stanford NLP)
- **GitHub**: `stanfordnlp/dspy`
- **Relevance**: **High**
- **Approach**: Treats prompts and LLM behavior as *learnable parameters*. Prompts are generated/optimized via examples and feedback loops. Supports prompt composition via module stacking. Generates different prompts for different models.
- **Key innovation**: Adaptive prompt generation — learns prompt variants for target model.
- **Limitations**: Focuses on optimization over composition; requires training examples; not user-customizable in traditional sense.
- **Overlap with BMAD proposal**: Multi-model adaptation, treating prompts as compilable. Different approach (learned vs authored).

#### Microsoft Prompt Flow
- **GitHub**: `microsoft/promptflow`
- **Relevance**: **Medium**
- **Approach**: DAG-based prompt orchestration with Jinja2-based templating within node definitions. YAML-based prompt definitions with conditional flows. Variable substitution and type checking. Runtime context injection.
- **Limitations**: Primarily an orchestration tool; not a pure prompt composition system; lacks user customization override system.
- **Overlap with BMAD proposal**: Conditional flows, variable substitution. Missing: fragment composition, override system, multi-model variants.

#### Promptfoo
- **GitHub**: `promptfoo/promptfoo`
- **Relevance**: **Medium**
- **Approach**: Prompt testing framework. Tests prompt outputs; doesn't compose them.
- **Overlap with BMAD proposal**: Enables prompt-as-code culture; useful as an eval harness for compiled prompt quality testing (the autoresearch loop).

#### Cline
- **GitHub**: `cline/cline`
- **Relevance**: **Medium**
- **Approach**: VS Code extension with implicit prompt composition based on agent role, task context, file system state, conversation history. Limited prompt override via `custom_instructions`.
- **Overlap with BMAD proposal**: Demonstrates JIT prompt assembly; limited customization framework.

#### Marvin (Prefect Labs)
- **GitHub**: `PrefectHQ/marvin`
- **Relevance**: **Low-Medium**
- **Approach**: Uses pydantic models + docstrings as prompt source. Implicit prompt generation from function signatures. Model adaptation.
- **Limitations**: Prompt generation is implicit; not user-customizable; limited multi-agent support.

#### Dust.tt
- **Relevance**: **Medium**
- **Approach**: Visual prompt composition with workflow builder. Blocks represent prompt fragments; chains show data flow. Server-side compilation of visual workflows into prompts.
- **Limitations**: Closed-source; UI-first (not code-first); limited programmatic access.

### Commercial / Proprietary

#### Cursor IDE
- **Relevance**: **Medium-High**
- **Mechanism**: Users customize `.cursor/rules` (YAML). System composes base prompt + user rules + file context. No public documentation on composition pipeline.
- **Gap**: Unclear if this extends to multi-agent prompt composition. No override safety or drift detection.

#### OpenAI Assistants API
- **Relevance**: **Low**
- **Composition**: Limited — mostly string concatenation. No merge strategy for user customizations.

#### Anthropic's Constitutional AI
- **Relevance**: Conceptual
- **Approach**: Layered prompt system with constitutional constraints. Foundational work on prompt composition patterns, but not a user-facing tool.

### Multi-Agent Frameworks (CrewAI, AutoGen, LangChain Agents)

All handle prompts simplistically:
- **CrewAI**: Role definition → string concatenation (no composition)
- **AutoGen**: System message + user message (basic)
- **LangChain Agent**: Template + tools list (Jinja2 rendering)

**No systematic multi-agent prompt assembly framework exists** that composes agent prompts deterministically from reusable fragments.

---

## 4. Prompt Composition Patterns in Practice

### Pattern 1: Fragment-Based Composition
- Merge base + override with conflict detection
- Examples: Cursor rules, some internal systems
- **Status**: Ad-hoc implementations, no standard

### Pattern 2: Jinja2-Based Templating
- Jinja render at runtime with context dict
- Examples: Prompt Flow, many custom frameworks
- **Limitations**: No multi-model adaptation, no user override semantics

### Pattern 3: Component-Based (MDX-Like)
- **Status**: Conceptual; no major adoption; would require MDX → prompt compiler
- **Potential**: Highest for treating prompts as structured source code
- **The BMAD proposal would be the first production implementation of this pattern**

### Pattern 4: DAG-Based Dependency Resolution
- Prompts as DAG nodes with dependencies, model variants, user overrides
- **Status**: Theoretical; no production implementation found

---

## 5. Summary Matrix

| Project | Composition | Compilation | User Override | Multi-Model | Multi-Agent | Open Source |
|---|---|---|---|---|---|---|
| **Prompt Flow** | ✓ (YAML DAG) | ✓ (Jinja) | ✗ | Partial | ✗ | ✓ |
| **DSPy** | ✗ | ✓ (Learned) | ✗ | ✓ | ✗ | ✓ |
| **Cursor Rules** | ✓ (File append) | ✗ | Basic | ✗ | ✗ | ✗ |
| **Cline** | ✓ (Context) | ✓ (JIT) | Basic | ✗ | Partial | ✓ |
| **CrewAI** | ✓ (Role) | ✗ | ✗ | ✗ | Basic | ✓ |
| **Dust.tt** | ✓ (Visual) | ✓ (Server) | ✗ | ✗ | ✗ | ✗ |
| **Marvin** | ✓ (Type-based) | ✓ (Implicit) | ✗ | ✓ | ✗ | ✓ |
| **BMAD Proposal** | ✓ (MDX fragments) | ✓ (Build + JIT) | ✓ (Full) | ✓ (Planned) | ✓ (Planned) | ✓ |

---

## 6. Gaps the BMAD Proposal Addresses

The research confirms no existing project covers:

1. **Standard format for composable prompt fragments** — BMAD proposes restricted MDX with an allowlisted component set
2. **Semantic merge strategy for user overrides** — BMAD proposes shadow directory + compile manifest with drift detection
3. **Deterministic multi-agent assembly** — BMAD proposes JIT compilation for subagent context
4. **Cross-model adaptation** via build-time conditional rendering — BMAD proposes `<If ide="...">` / `<Switch on="model">`
5. **Upgrade safety** for user customizations — BMAD proposes compile manifest with hash-based drift detection and reporting

---

## 7. Projects Worth Monitoring

| Project | Why | Watch for |
|---|---|---|
| **DSPy** | Closest to "compiled prompts" — learned/optimized rather than authored. Could complement BMAD's authored approach with automated optimization. | Integration patterns, model adaptation API |
| **Promptfoo** | Prompt testing — natural eval harness for compiled prompt quality. | Plugin/integration API for custom prompt sources |
| **Prompt Flow** | Microsoft-backed orchestration. If they add a composition layer, it would be significant. | Composition features, user override support |
| **Cursor / Claude Code** | IDE-side prompt assembly is the JIT runtime target. Their APIs determine what's possible for tool-backed skill loading. | Skill invocation APIs, MCP tool-backed prompts |

---

## 8. Implications for the Proposal

### Validates the approach
- The gap is real and well-documented. No existing project fills it.
- Component-based composition (Pattern 3) is identified as the highest-potential approach but has no production implementation — BMAD would be first.

### Suggests additions to consider
- **Prompt testing integration**: The proposal should mention Promptfoo or similar as the eval harness for the autoresearch optimization loop.
- **DSPy complementarity**: The static/JIT compilation in BMAD (authored prompts) and DSPy's learned optimization are complementary, not competing. A future integration could use DSPy to optimize compiled fragments.
- **Token budget awareness**: Several sources mention context window management as a compilation concern. The compiler could warn when a compiled prompt exceeds a target model's context window.

### Reinforces key decisions
- **Restricted MDX as default**: The research confirms no standard exists; being first means defining the format. Restrictive-by-default is correct for ecosystem adoption.
- **JIT as future direction**: Multiple projects (Cline, Cursor) already do primitive JIT assembly. The trend validates BMAD's JIT roadmap.
- **Override drift detection**: No existing project handles this. It's a genuine differentiator.
