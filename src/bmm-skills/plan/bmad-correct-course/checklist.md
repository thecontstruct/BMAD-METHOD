# Change Navigation Checklist

<critical>This checklist is executed as part of: ./SKILL.md</critical>
<critical>Work through each section systematically with the user, recording findings and impacts</critical>

<checklist>

<section n="1" title="Understand the Trigger and Context">

<check-item id="1.1">
<prompt>Identify the triggering ticket or legacy story that revealed this issue</prompt>
<action>In ticket-tree mode, document the ticket ref, epic folder, current state, and brief description. Without a tree, document the story ID and brief description.</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="1.2">
<prompt>Define the core problem precisely</prompt>
<action>Categorize issue type:</action>
  - Technical limitation discovered during implementation
  - New requirement emerged from stakeholders
  - Misunderstanding of original requirements
  - Strategic pivot or market change
  - Failed approach requiring different solution
<action>Write clear problem statement</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="1.3">
<prompt>Assess initial impact and gather supporting evidence</prompt>
<action>Collect concrete examples, error messages, stakeholder feedback, or technical constraints</action>
<action>Document evidence for later reference</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<halt-condition>
<action if="trigger is unclear">HALT: "Cannot proceed without understanding what caused the need for change"</action>
<action if="no evidence provided">HALT: "Need concrete evidence or examples of the issue before analyzing impact"</action>
</halt-condition>

</section>

<section n="2" title="Ticket-tree or Epic Impact Assessment">

<check-item id="2.1">
<prompt>Evaluate the current epic folder containing the triggering ticket, or the legacy epic containing the trigger story</prompt>
<action>In ticket-tree mode, resolve each affected ref and its prerequisites and dependents before assessing scope. Can this epic still be completed as originally planned?</action>
<action>If no, what modifications are needed?</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="2.2">
<prompt>Determine required epic-level and ticket-level changes</prompt>
<action>Check each scenario:</action>
  - Rescope, split, resequence, or update prerequisites for planned ticket-tree work
  - Add new epic to address the issue
  - Drop or defer work that's no longer viable, including dependent remediation
  - Modify existing epic scope or acceptance criteria in legacy mode
  - Completely redefine epic based on new understanding
<action>Document specific changes needed. In ticket-tree mode, preserve ids and propose follow-on work instead of rewriting active, built, done, or dropped tickets.</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="2.3">
<prompt>Review remaining planned ticket-tree work or epics for required changes</prompt>
<action>Check each future ticket or epic for impact</action>
<action>Identify dependencies that may be affected</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="2.4">
<prompt>Check if issue invalidates future tickets or epics, or necessitates new ones</prompt>
<action>Does this change make any planned tickets or epics obsolete?</action>
<action>Are new tickets or epics needed to address gaps created by this change?</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="2.5">
<prompt>Consider if ticket, epic order, or priority should change</prompt>
<action>Should tickets or epics be resequenced based on this issue?</action>
<action>Do priorities need adjustment?</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

</section>

<section n="3" title="Artifact Conflict and Impact Analysis">

<check-item id="3.1">
<prompt>Check PRD for conflicts</prompt>
<action>Does issue conflict with core PRD goals or objectives?</action>
<action>Do requirements need modification, addition, or removal?</action>
<action>Is the defined MVP still achievable or does scope need adjustment?</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="3.2">
<prompt>Review Architecture document for conflicts</prompt>
<action>Check each area for impact:</action>
  - System components and their interactions
  - Architectural patterns and design decisions
  - Technology stack choices
  - Data models and schemas
  - API designs and contracts
  - Integration points
<action>Document specific architecture sections requiring updates</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="3.3">
<prompt>Examine UI/UX specifications for conflicts</prompt>
<action>Check for impact on:</action>
  - User interface components
  - User flows and journeys
  - Wireframes or mockups
  - Interaction patterns
  - Accessibility considerations
<action>Note specific UI/UX sections needing revision</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="3.4">
<prompt>Consider impact on other artifacts</prompt>
<action>Review additional artifacts for impact:</action>
  - Deployment scripts
  - Infrastructure as Code (IaC)
  - Monitoring and observability setup
  - Testing strategies
  - Documentation
  - CI/CD pipelines
<action>Document any secondary artifacts requiring updates</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

</section>

<section n="4" title="Path Forward Evaluation">

<check-item id="4.1">
<prompt>Evaluate Option 1: Direct Adjustment</prompt>
<action>Can the issue be addressed by modifying existing stories?</action>
<action>Can new stories be added within the current epic structure?</action>
<action>Would this approach maintain project timeline and scope?</action>
<action>Effort estimate: [High/Medium/Low]</action>
<action>Risk level: [High/Medium/Low]</action>
<status>[ ] Viable / [ ] Not viable</status>
</check-item>

<check-item id="4.2">
<prompt>Evaluate Option 2: Potential Rollback</prompt>
<action>Would reverting recently completed stories simplify addressing this issue?</action>
<action>Which stories would need to be rolled back?</action>
<action>Is the rollback effort justified by the simplification gained?</action>
<action>Effort estimate: [High/Medium/Low]</action>
<action>Risk level: [High/Medium/Low]</action>
<status>[ ] Viable / [ ] Not viable</status>
</check-item>

<check-item id="4.3">
<prompt>Evaluate Option 3: PRD MVP Review</prompt>
<action>Is the original PRD MVP still achievable with this issue?</action>
<action>Does MVP scope need to be reduced or redefined?</action>
<action>Do core goals need modification based on new constraints?</action>
<action>What would be deferred to post-MVP if scope is reduced?</action>
<action>Effort estimate: [High/Medium/Low]</action>
<action>Risk level: [High/Medium/Low]</action>
<status>[ ] Viable / [ ] Not viable</status>
</check-item>

<check-item id="4.4">
<prompt>Select recommended path forward</prompt>
<action>Based on analysis of all options, choose the best path</action>
<action>Provide clear rationale considering:</action>
  - Implementation effort and timeline impact
  - Technical risk and complexity
  - Impact on team morale and momentum
  - Long-term sustainability and maintainability
  - Stakeholder expectations and business value
<action>Selected approach: [Option 1 / Option 2 / Option 3 / Hybrid]</action>
<action>Justification: [Document reasoning]</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

</section>

<section n="5" title="Sprint Change Proposal Components">

<check-item id="5.1">
<prompt>Create identified issue summary</prompt>
<action>Write clear, concise problem statement</action>
<action>Include context about discovery and impact</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="5.2">
<prompt>Document ticket-tree or epic impact and artifact adjustment needs</prompt>
<action>Summarize findings from Ticket-tree or Epic Impact Assessment (Section 2)</action>
<action>Summarize findings from Artifact Conflict Analysis (Section 3)</action>
<action>Be specific about what changes are needed and why</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="5.3">
<prompt>Present recommended path forward with rationale</prompt>
<action>Include selected approach from Section 4</action>
<action>Provide complete justification for recommendation</action>
<action>Address trade-offs and alternatives considered</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="5.4">
<prompt>Define PRD MVP impact and high-level action plan</prompt>
<action>State clearly if MVP is affected</action>
<action>Outline major action items needed for implementation</action>
<action>Identify dependencies and sequencing</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="5.5">
<prompt>Establish agent handoff plan</prompt>
<action>Identify which roles/agents will execute the changes:</action>
  - `bmad-preview-ticketing` (for approved ticket-tree operations)
  - Developer agent (for implementation)
  - Product Owner / Developer (for backlog changes)
  - Product Manager / Architect (for strategic changes)
<action>Define responsibilities for each role</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

</section>

<section n="6" title="Final Review and Handoff">

<check-item id="6.1">
<prompt>Review checklist completion</prompt>
<action>Verify all applicable sections have been addressed</action>
<action>Confirm all [Action-needed] items have been documented</action>
<action>Ensure analysis is comprehensive and actionable</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="6.2">
<prompt>Verify Sprint Change Proposal accuracy</prompt>
<action>Review complete proposal for consistency and clarity</action>
<action>Ensure all recommendations are well-supported by analysis</action>
<action>Check that proposal is actionable and specific</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="6.3">
<prompt>Obtain explicit user approval</prompt>
<action>Present complete proposal to user</action>
<action>Get clear yes/no approval for proceeding</action>
<action>Document approval and any conditions</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<check-item id="6.4">
<prompt>Confirm next steps and handoff plan</prompt>
<action>Review handoff responsibilities with user</action>
<action>In ticket-tree mode, hand the approved operations list to `bmad-preview-ticketing`; do not edit ticket files, plans, `tickets.toml`, or ticket status from Correct Course.</action>
<action>Ensure all stakeholders understand their roles</action>
<action>Confirm timeline and success criteria</action>
<status>[ ] Done / [ ] N/A / [ ] Action-needed</status>
</check-item>

<halt-condition>
<action if="any critical section cannot be completed">HALT: "Cannot proceed to proposal without complete impact analysis"</action>
<action if="user approval not obtained">HALT: "Must have explicit approval before implementing changes"</action>
<action if="handoff responsibilities unclear">HALT: "Must clearly define who will execute the proposed changes"</action>
</halt-condition>

</section>

</checklist>

<execution-notes>
<note>This checklist is for SIGNIFICANT changes affecting project direction</note>
<note>Work interactively with user - they make final decisions</note>
<note>Be factual, not blame-oriented when analyzing issues</note>
<note>Handle changes professionally as opportunities to improve the project</note>
<note>Maintain conversation context throughout - this is collaborative work</note>
</execution-notes>
