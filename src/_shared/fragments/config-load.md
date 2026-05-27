Load config from `{{config_path}}` and resolve:

- `project_name`, `user_name`
- `communication_language`, `document_output_language`
- `user_skill_level`
- `implementation_artifacts`
- `planning_artifacts`
- `project_knowledge`
- `date` as system-generated current datetime
- `project_context` = `**/project-context.md` (load if exists)
- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`
- Language MUST be tailored to `{user_skill_level}`
- Generate all documents in `{document_output_language}`
- DOCUMENT OUTPUT: Updated epics, stories, or PRD sections. Clear, actionable changes. User skill level (`{user_skill_level}`) affects conversation style ONLY, not document updates.
