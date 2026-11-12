# UI Source: Magic UI

> Default component source for web front ends built with React (Next.js or Vite), TypeScript and Tailwind CSS. Copy the parts that apply into `docs/design-rules.md` → `## Components` and `docs/gates/`. Not for native iOS/Android or non-React stacks: there the platform's own components apply.

Magic UI ([magicui.design](https://magicui.design), [github.com/magicuidesign/magicui](https://github.com/magicuidesign/magicui)) is a free, MIT-licensed library of 150+ animated React components (marquee, blur fade, bento grid, animated beam, globe, particles, shiny button, magic card …), built on Tailwind CSS and Motion and distributed through the shadcn registry. Magic UI Pro (paid blocks and templates) is not used unless the owner buys it. [VERIFY: component count, licence and install syntax against the docs before the design station closes.]

## Install contract

1. Once per project, in the task that creates the web shell: `npx shadcn@latest init` (writes `components.json`, the `cn` helper and the CSS variables).
2. Per component, in the task that needs it: `npx shadcn@latest add @magicui/<component-slug>`, e.g. `npx shadcn@latest add @magicui/marquee`. The CLI copies the source into the project and installs its dependencies (usually `motion`).
3. The first add brings new dependencies: the task asks for `pl_approval` (new_dependency) before it runs the command; `package.json` and the lockfile are in its scope.
4. Never hand-copy component code from the website and never edit the generated files to restyle them; restyle through the design tokens (CSS variables) or a wrapper component in the project's own UI folder.

## Design rules for Magic UI

- **Where motion belongs:** landing pages, hero sections, empty states and onboarding. Dense app screens (tables, forms, settings) stay calm: at most one moving element in view.
- **Reduced motion:** every animated component respects `prefers-reduced-motion`; check it per component and wrap it where it does not.
- **Tokens first:** colours, radii and durations come from `docs/design-rules.md`; Magic UI's defaults are replaced, not mixed.
- **Performance:** heavy effects (globe, particles, canvas backgrounds) load lazily and stay out of the first screen on mobile unless the design rules say otherwise; they count against the Core Web Vitals budget.
- **Accessibility:** decorative effects get `aria-hidden`; text inside animated components stays readable and selectable; contrast is checked on the moving background, not the static one.

## `docs/design-rules.md` → `## Components`

| Component | Source | Install | Used in | Notes |
| --- | --- | --- | --- | --- |
| `<Marquee>` | Magic UI | `npx shadcn@latest add @magicui/marquee` | `<Landing: logos>` | `<pauses on hover; reduced motion → static row>` |
| `<Button>` | shadcn/ui | `npx shadcn@latest add button` | everywhere | `<tokens: --primary, radius md>` |

Every component the product uses is listed once; a component not in the table is not used.

## Gates

- `types`, `lint`, `tests` as usual; the `e2e` flow runs once with reduced motion emulated (Playwright: `reducedMotion: 'reduce'`).
- `a11y` (axe/Lighthouse) on every page with an animated component.
- Licence: Magic UI and shadcn/ui are MIT; list them in the licence notice (`REL-09`).

## Agents

The install contract above stays the rule either way: a skill or an MCP server helps an agent find components, it never replaces `npx shadcn@latest add`, the `## Components` table or the `pl_approval` for a new dependency. Both are optional; adding one is the owner's call, because it widens what agents can reach (`docs/guard-limits.md`).

**DeepSeek Harness**

- Agent skill from the Magic UI repository: `npx skills add magicuidesign/magicui --skill magic-ui`. [VERIFY: the folder DeepSeek Harness reads skills from.]
- MCP server for browsing the registry: see [magicui.design/docs/mcp](https://magicui.design/docs/mcp); DeepSeek Harness connects MCP servers through its MCP client.

**Claude Code**

- MCP server: the shadcn MCP server with the Magic UI registry (as of 2026-11-12, [magicui.design/docs/mcp](https://magicui.design/docs/mcp), [ui.shadcn.com/docs/mcp](https://ui.shadcn.com/docs/mcp)).
  1. In `components.json` → `registries`: `"@magicui": "https://magicui.design/r/{name}.json"`.
  2. `npx shadcn@latest mcp init --client claude`, or by hand a project `.mcp.json`:
     ```json
     { "mcpServers": { "shadcn": { "command": "npx", "args": ["shadcn@latest", "mcp"] } } }
     ```
  3. Restart the session; `/mcp` shows `shadcn` as connected. Claude Code asks the owner once before it starts a server from a project `.mcp.json`.
  `components.json` and `.mcp.json` belong to the task that creates the web shell: list them in its scope.
- Agent skill: `npx skills add magicuidesign/magicui --skill magic-ui`, choosing Claude Code as the target, puts it under `.claude/skills/`; commit it with the project so every session and subagent gets it. [VERIFY: the skill name and the CLI's Claude Code target against the Magic UI repository.]
- The `polier:frontend-builder` and `polier:designer` subagents inherit the session's MCP servers and skills; nothing else is needed.
