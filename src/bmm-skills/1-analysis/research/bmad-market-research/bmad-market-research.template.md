---
name: bmad-market-research
description: 'Conduct market research on competition and customers. Use when the user says they need market research'
artifacts:
  - path: research.template.md
    source: research.template.md
    kind: scaffold-verbatim
  - path: steps/step-01-init.md
    source: steps/step-01-init.md
    kind: scaffold-verbatim
  - path: steps/step-02-customer-behavior.md
    source: steps/step-02-customer-behavior.md
    kind: scaffold-verbatim
  - path: steps/step-03-customer-pain-points.md
    source: steps/step-03-customer-pain-points.md
    kind: scaffold-verbatim
  - path: steps/step-04-customer-decisions.md
    source: steps/step-04-customer-decisions.md
    kind: scaffold-verbatim
  - path: steps/step-05-competitive-analysis.md
    source: steps/step-05-competitive-analysis.md
    kind: scaffold-verbatim
  - path: steps/step-06-research-completion.md
    source: steps/step-06-research-completion.md
    kind: scaffold-verbatim
---

# Market Research Workflow

**Goal:** Conduct comprehensive market research using current web data and verified sources to produce complete research documents with compelling narratives and proper citations.

**Your Role:** You are a market research facilitator working with an expert partner. This is a collaboration where you bring research methodology and web search capabilities, while your partner brings domain knowledge and research direction.

## Conventions

- Bare paths (e.g. `steps/step-01-init.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## PREREQUISITE

**⛔ Web search required.** If unavailable, abort and tell the user.

## On Activation

### Step 1: Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>
### Step 2: Execute Prepend Steps

Execute each entry in `{workflow.activation_steps_prepend}` in order before proceeding.

### Step 3: Load Persistent Facts

<<include path="_shared/fragments/persistent-facts.md">>
### Step 4: Load Config

Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:
- Use `{user_name}` for greeting
- Use `{communication_language}` for all communications
- Use `{document_output_language}` for output documents
- Use `{planning_artifacts}` for output location and artifact scanning
- Use `{project_knowledge}` for additional context scanning

### Step 5: Greet the User

Greet `{user_name}`, speaking in `{communication_language}`.

### Step 6: Execute Append Steps

Execute each entry in `{workflow.activation_steps_append}` in order.

Activation is complete. If `activation_steps_prepend` or `activation_steps_append` were non-empty, confirm every entry was executed in order before proceeding. Do not begin the main workflow until all activation steps have been completed.

## QUICK TOPIC DISCOVERY

"Welcome {user_name}! Let's get started with your **market research**.

**What topic, problem, or area do you want to research?**

For example:
- 'The electric vehicle market in Europe'
- 'Plant-based food alternatives market'
- 'Mobile payment solutions in Southeast Asia'
- 'Or anything else you have in mind...'"

### Topic Clarification

Based on the user's topic, briefly clarify:
1. **Core Topic**: "What exactly about [topic] are you most interested in?"
2. **Research Goals**: "What do you hope to achieve with this research?"
3. **Scope**: "Should we focus broadly or dive deep into specific aspects?"

## ROUTE TO MARKET RESEARCH STEPS

After gathering the topic and goals:

1. Set `research_type = "market"`
2. Set `research_topic = [discovered topic from discussion]`
3. Set `research_goals = [discovered goals from discussion]`
4. Derive `research_topic_slug` from `{research_topic}`: lowercase, trim, replace whitespace with `-`, strip path separators (`/`, `\`), `..`, and any character that is not alphanumeric, `-`, or `_`. Collapse repeated `-` and strip leading/trailing `-`. If the result is empty, use `untitled`.
5. Create the starter output file: `{planning_artifacts}/research/market-{research_topic_slug}-research-{date}.md` with exact copy of the `./research.template.md` contents
6. Load: `./steps/step-01-init.md` with topic context

**Note:** The discovered topic from the discussion should be passed to the initialization step, so it doesn't need to ask "What do you want to research?" again - it can focus on refining the scope for market research.

**✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`**
