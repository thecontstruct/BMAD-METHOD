# Claude Code Root
Note: claudecode

- **Preferred — sub-agent (Task tool):** test-spawn Dispatch via the Task tool; the sub-agent receives only the prompt you supply, returns a single final message, and has no view into the parent conversation. If the sub-agent needs a working directory, file paths, or returned-artifact shape, name them explicitly in the prompt.
- **Fallback — inline:** test-fallback
