# Design Rules: canvas-mini

> Binding for every UI change. Tokens live in `packages/ui-kit/src/theme.css`; a deviation needs approval before any UI code.

## Tokens

UI code uses tokens only. No raw hex, `rgba()` or pixel literals outside the theme file.

| Group | Tokens | Values | Use |
|---|---|---|---|
| Spacing | `--space-1` … `--space-8` | 4, 8, 12, 16, 24, 32, 48 px | padding, gaps, offsets |
| Type | `--text-sm`, `--text-md`, `--text-lg` | 13, 15, 22 px | labels, body, headings |
| Radii | `--radius-sm`, `--radius-md`, `--radius-lg` | 8, 12, 16 px | controls, cards, panels |
| Motion | `--motion-fast`, `--motion-base`, `--motion-slow` | 120, 180, 240 ms | hover, panels, overlays |
| Colour | `--bg`, `--fg`, `--muted`, `--border`, `--accent`, `--danger` | theme values | surfaces, text, borders, primary action, errors |

- One spacing scale on a 4 px grid; never 5, 7, 10 px. Minimum text size 11 px; minimum target 44 × 44 px on touch, 32 × 32 px with a mouse.
- A missing token is added to the theme file with approval — never inline in a component.

## Colour and contrast

- Semantic tokens only (`--bg`, `--fg`, `--muted`, `--border`, `--accent`, `--danger`); no colour by hex in components.
- Contrast at least 4.5:1 for body text, 3:1 for large text, icons and control boundaries (WCAG AA).
- Colour is never the only signal; pair it with text, icon or shape.

## States

Every interactive element defines all applicable states: rest, hover, pressed, focus, selected, dragging, disabled, saving, error.

- Focus is always visible: `outline: 2px solid var(--accent); outline-offset: 2px`. Never `outline: none` without a replacement.
- Hover and pressed use tokens; pressed may scale to 0.97; disabled is 0.4 opacity with no hover.
- Saving and error keep the layout stable; an error stays visible and keeps the input.
- Motion comes from the motion tokens; animate `transform` and `opacity`, never layout properties. `prefers-reduced-motion: reduce` removes transitions.

## Layout

- Breakpoints: 390, 768, 1024, 1440 px. No horizontal scroll at 390 px.
- The toolbar is fixed at the top of the viewport: 48 px high (`--space-8`), full width, 16 px horizontal padding (`--space-4`).
- The stage fills the remaining viewport; no floating panel without approval.
- Reuse existing components, icons and spacing; a new component needs a reason in the brief.

## Accessibility minimums

- Every control is keyboard reachable, has a visible focus and an accessible name (`aria-label` or visible text).
- Semantic HTML first; images have alt text; form errors are text, not colour only.
- No text below 11 px, no truncated text without ellipsis, no emoji as an icon.

## How a brief cites these rules

- The brief's `## UI specification` lists target values in px and ms and cites every token by name and value from this file, e.g. `padding: 16px (--space-4)`.
- A value in the brief that is not a token here is a finding, not a new rule. A UI task without numbers is not ready.
- Screenshots: `reviews/evidence/<ID>-<view>-before-<viewport>.png` and `…-after-…` at 1440 × 900 and 390 × 844.

## Do not

- Add hex/rgba colours, fonts or spacing values outside the tokens.
- Remove a focus outline, animate layout properties, or use bounce/spring animations.
- Ship a state the brief does not specify.
- Use placeholder text in UI.
- Change other views as a side effect.
