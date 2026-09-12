# Maker Swap Decisions

- [Phase 1] Use one FastAPI/Jinja2 service on Render - minimizes tooling and deployment overhead within 72 hours.
- [Phase 1] Store the small seeded catalogue in JSON and memory - a database adds no assessment value.
- [Phase 1] Keep all AI calls and `CLASSGW_KEY` on the backend - prevents browser and repository credential exposure.
- [Phase 1] Exclude accounts, payments, logistics, and multi-vendor support - they are outside the assessment's core flow.
- [Phase 1] Treat listing location as plain pickup-area text only - avoids introducing seller identities or profile structure.
- [Phase 2] Validate seeded JSON with a strict Pydantic listing schema at load time - malformed catalogue data should fail visibly.
- [Phase 2] Use local reusable SVG category artwork instead of remote photos - keeps the deployed browse flow self-contained and reliable.
- [Phase 2] Publish a minimal truthful `/notes` page before its full Phase 5 write-up - the footer must never point to a placeholder or missing page.
- [Phase 3] Batch and cache one embedding per seeded listing, then cosine-rank exact catalogue records for each embedded query - repeat searches need one model call and cannot invent products.
- [Phase 3] Request `openai/text-embedding-3-small` because this gateway rejects the unqualified ID as unpriced; its successful response confirms the underlying `text-embedding-3-small` model.
- [Phase 3] Return the four strongest cosine matches with no arbitrary similarity cutoff - one focused desktop row avoids weak tail results, while relative ranking stays stable across query types.
- [Phase 3] Supersede the no-cutoff approach with a 0.35 cosine floor - real unrelated probes peaked at 0.31, while indirect valid matches began at 0.36, so empty results are more honest than weak forced matches.
- [Phase 3] Add truthful renovation, DIY and home-improvement tags to both workshop tools instead of lowering the global floor - improves vague relevant intent without reviving unrelated matches.
- [Phase 3] Supersede one catalogue vector with two cached views per listing (full details plus concise title/category/tags) - max-view scoring preserves detailed searches while giving specific use cases enough semantic weight.
- [Phase 3] Version the search JavaScript URL - prevents browser or Render caches from retaining obsolete interaction logic after a deploy.
- [Phase 1] Exclude the supplied assessment PDF from Git history - it is reference material, not public application source.
