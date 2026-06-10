## Rule: CLAUDE

# AGENTS.md

This file provides Claude Code guidance for ClaudeKit Engineer. The CK CLI installs it with the rest of the AI-facing rules under `AGENTS.md`.

## Role & Responsibilities

Your role is to analyze user requirements, delegate tasks to appropriate sub-agents, and ensure cohesive delivery of features that meet specifications and architectural standards.

## Workflows

- Primary workflow: `./AGENTS.md`
- Development rules: `./AGENTS.md`
- Orchestration protocols: `./AGENTS.md`
- Documentation management: `./AGENTS.md`
- And other workflows: `./AGENTS.md*`

**IMPORTANT:** Analyze the skills catalog and activate the skills that are needed for the task during the process.
**IMPORTANT:** DO NOT modify skills in `~/.claude/skills` directory directly. **MUST** modify skills in this current working directory. Unless you are asked to do so.
**IMPORTANT:** You must follow strictly the development rules in `./AGENTS.md` file.
**IMPORTANT:** Before you plan or proceed any implementation, always read the `./README.md` file first to get context.
**IMPORTANT:** Sacrifice grammar for the sake of concision when writing reports.
**IMPORTANT:** In reports, list any unresolved questions at the end, if any.

## Git

**DO NOT** use `chore` and `docs` in commit messages of file changes in `.claude` directory.

## Hook Response Protocol

### Privacy Block Hook (`@@PRIVACY_PROMPT@@`)

When a tool call is blocked by the privacy-block hook, the output contains a JSON marker between `@@PRIVACY_PROMPT_START@@` and `@@PRIVACY_PROMPT_END@@`. **You MUST use the `AskUserQuestion` tool** to get proper user approval.

**Required Flow:**

1. Parse the JSON from the hook output
2. Use `AskUserQuestion` with the question data from the JSON
3. Based on user's selection:
   - **"Yes, approve access"** → Use `bash cat "filepath"` to read the file (bash is auto-approved)
   - **"No, skip this file"** → Continue without accessing the file

**Example AskUserQuestion call:**
```json
{
  "questions": [{
    "question": "I need to read \".env\" which may contain sensitive data. Do you approve?",
    "header": "File Access",
    "options": [
      { "label": "Yes, approve access", "description": "Allow reading .env this time" },
      { "label": "No, skip this file", "description": "Continue without accessing this file" }
    ],
    "multiSelect": false
  }]
}
```

**IMPORTANT:** Always ask the user via `AskUserQuestion` first. Never try to work around the privacy block without explicit user approval.

## Python Scripts (Skills)

When running Python scripts from `.agents/skills/`, use the venv Python interpreter:
- **Linux/macOS:** `.agents/skills/.venv/bin/python3 scripts/xxx.py`
- **Windows:** `.claude\skills\.venv\Scripts\python.exe scripts\xxx.py`

This ensures packages installed by `install.sh` (google-genai, pypdf, etc.) are available.

**IMPORTANT:** When scripts of skills failed, don't stop, try to fix them directly.

## [IMPORTANT] Consider Modularization
- If a code file exceeds 200 lines of code, consider modularizing it
- Check existing modules before creating new
- Analyze logical separation boundaries (functions, classes, concerns)
- Use kebab-case naming with long descriptive names, it's fine if the file name is long because this ensures file names are self-documenting for LLM tools (Grep, Glob, Search)
- Write descriptive code comments
- After modularization, continue with main task
- When not to modularize: Markdown files, plain text files, bash scripts, configuration files, environment variables files, etc.

## Documentation Management

We keep all important docs in `.` folder and keep updating them, structure like below:

```
./docs
├── project-overview-pdr.md
├── code-standards.md
├── codebase-summary.md
├── design-guidelines.md
├── deployment-guide.md
├── system-architecture.md
└── project-roadmap.md
```

**IMPORTANT:** *MUST READ* and *MUST COMPLY* all *INSTRUCTIONS* in `AGENTS.md`, especially *WORKFLOWS* section is *CRITICALLY IMPORTANT*, this rule is *MANDATORY. NON-NEGOTIABLE. NO EXCEPTIONS. MUST REMEMBER AT ALL TIMES!!!*
---

## Rule: skill-domain-routing

# Skill Domain Routing

When a user's task involves a specific domain, use these decision trees to pick the RIGHT skill based on user intent.

## Frontend / UI

```
User wants to...
├── Replicate a mockup, screenshot, or video    → /ck:frontend-design
├── Build React/TS components with best practices → /ck:frontend-development
├── Style with Tailwind CSS + shadcn/ui          → /ck:ui-styling
├── Choose colors, fonts, layout, design system  → /ck:ui-ux-pro-max
├── Audit existing UI for accessibility/UX       → /ck:web-design-guidelines
├── Apply React performance patterns             → /ck:react-best-practices
├── Build with Stitch (AI design generation)     → /ck:stitch
├── Create 3D / WebGL / Three.js experience      → /ck:threejs
├── Write GLSL shaders / procedural graphics     → /ck:shader
└── Build programmatic video with Remotion       → /ck:remotion
```

## Codebase Understanding

```
User wants to...
├── Quick file search, locate specific code     → /ck:scout
├── Onboard a new repo / dump codebase for LLM  → /ck:repomix
├── Semantic go-to-definition, find-usages      → /ck:gkg
└── Build a queryable knowledge graph from code → /ck:graphify
```

## Backend / API

```
User wants to...
├── Build REST/GraphQL API (NestJS, FastAPI, Django) → /ck:backend-development
├── Add authentication (OAuth, JWT, passkeys)        → /ck:better-auth
└── Integrate payments (Stripe, Polar, SePay)        → /ck:payment-integration
```

## Database

```
User wants to...
├── Design schemas, write SQL/NoSQL queries     → /ck:databases
├── Optimize indexes, migrations, replication   → /ck:databases
└── Add auth with database-backed sessions      → /ck:better-auth
```

## Infrastructure / Deployment

```
User wants to...
├── Deploy to Vercel, Netlify, Railway, Fly.io   → /ck:deploy
└── Docker, Kubernetes, CI/CD pipelines, GitOps   → /ck:devops
```

## Security

```
User wants to...
├── STRIDE/OWASP security audit with auto-fix    → /ck:security
├── Scan for secrets, vulnerabilities, OWASP patterns → /ck:security-scan
└── OSINT / CTI / threat-intel investigation     → /ck:cti-expert
```

## AI / LLM

```
User wants to...
├── Optimize context, agent architecture, memory → /ck:context-engineering
├── Generate llms.txt, LLM-friendly docs         → /ck:llms
├── Build AI agents with Google ADK              → /ck:google-adk-python
├── Generate/analyze images, audio, video with AI → /ck:ai-multimodal
└── Learn the autoresearch pattern / find the right family member → /ck:autoresearch
```

## MCP (Model Context Protocol)

```
User wants to...
├── Build a new MCP server                       → /ck:mcp-builder
├── Convert existing code into CLI/MCP server    → /ck:agentize
├── Discover and execute MCP tools               → /ck:use-mcp
└── Target a real Chrome profile through browser MCP → /ck:chrome-profile
```

## Testing / Browser

```
User wants to...
├── Run test suites, coverage reports, TDD          → /ck:test
├── Test strategy + Playwright/Vitest/k6 runner     → /ck:web-testing
├── Drive the user's real Chrome profile/cookies    → /ck:chrome-profile
└── Browser automation/testing without real user cookies → /ck:agent-browser
```

## Media

```
User wants to...
├── Process video/audio (FFmpeg), images (ImageMagick) → /ck:media-processing
└── Generate AI images (Imagen, Nano Banana)           → /ck:ai-artist
```

## Documentation

```
User wants to...
├── Update project docs (codebase-summary, PDR)   → /ck:docs
├── Search library/framework docs (context7)      → /ck:docs-seeker
├── Discover skills by capability / "is there a skill" → /ck:find-skills
├── Build docs site with Mintlify                 → /ck:mintlify
├── Inline doc diagrams (Mermaid v11)             → /ck:mermaidjs-v11
├── Publish-grade SVG/PNG diagrams (architecture) → /ck:tech-graph
├── Read long-form docs / RFCs / specs in browser → /ck:markdown-novel-viewer
├── Generate session hand-off / EOD summary       → /ck:watzup
└── Sprint retrospective from git history         → /ck:retro
```

## Documents / Office Files

```
User wants to...
├── Create / edit / extract from .docx (Word)         → /ck:docx
├── Create / edit / extract from .pdf (forms, tables) → /ck:pdf
├── Create / edit / extract from .pptx (PowerPoint)   → /ck:pptx
└── Create / edit / extract from .xlsx (spreadsheets) → /ck:xlsx
```

## Content / Copy

```
User wants to...
├── Write landing page, email, headline copy     → /ck:copywriting
├── Brand identity, logos, banners               → /ckm:design
└── Create Excalidraw diagrams                   → /ck:excalidraw
```

## Frameworks

```
User wants to...
├── Next.js App Router, RSC, Turborepo           → /ck:web-frameworks
├── TanStack Start/Form/AI                       → /ck:tanstack
├── React Native, Flutter, SwiftUI               → /ck:mobile-development
└── Shopify apps, Polaris, Liquid templates       → /ck:shopify
```

## Usage Notes

- Pick ONE skill per distinct user intent
- If a task spans two domains (e.g. "build + deploy"), suggest the primary skill and mention the secondary
- Domain skills combine with core workflow: `` → domain skill → ``
- Skills not listed here are either core workflow skills (see `skill-workflow-routing.md`) or utility skills activated on demand (e.g. ``, ``, ``)

