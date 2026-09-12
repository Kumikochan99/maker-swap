# Maker Swap Decisions

- [Phase 1] Use one FastAPI/Jinja2 service on Render - minimizes tooling and deployment overhead within 72 hours.
- [Phase 1] Store the small seeded catalogue in JSON and memory - a database adds no assessment value.
- [Phase 1] Keep all AI calls and `CLASSGW_KEY` on the backend - prevents browser and repository credential exposure.
- [Phase 1] Exclude accounts, payments, logistics, and multi-vendor support - they are outside the assessment's core flow.
- [Phase 1] Treat listing location as plain pickup-area text only - avoids introducing seller identities or profile structure.
- [Phase 2] Validate seeded JSON with a strict Pydantic listing schema at load time - malformed catalogue data should fail visibly.
- [Phase 2] Use local reusable SVG category artwork instead of remote photos - keeps the deployed browse flow self-contained and reliable.
- [Phase 1] Exclude the supplied assessment PDF from Git history - it is reference material, not public application source.
