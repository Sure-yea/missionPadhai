---
name: swiss-grid
description: >-
  Use this skill whenever designing, building, or improving frontend interfaces
  for this project. It defines the Swiss Grid design system: International
  Typographic Style with a 12-column grid, Inter Tight headings, Inter body
  text, high-contrast neutrals, and a single red (#DC2626) accent for all
  interactive elements. Activate when asked to create UI components, pages,
  layouts, or visual styling.
version: alpha
colors:
  primary: "#000000"
  secondary: "#555555"
  tertiary: "#DC2626"
  neutral: "#F5F5F5"
  surface: "#FFFFFF"
  on-primary: "#FFFFFF"
typography:
  display:
    fontFamily: Inter Tight
    fontSize: 4rem
    fontWeight: 700
    letterSpacing: "-0.03em"
  h1:
    fontFamily: Inter Tight
    fontSize: 2.25rem
    fontWeight: 700
    letterSpacing: "-0.02em"
  body:
    fontFamily: Inter
    fontSize: 0.95rem
    lineHeight: 1.55
  label:
    fontFamily: Inter
    fontSize: 0.75rem
    letterSpacing: "0.02em"
rounded:
  sm: 0px
  md: 0px
  lg: 0px
spacing:
  sm: 8px
  md: 16px
  lg: 32px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px 20px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.lg}"
    padding: 24px
---

# Swiss Grid Design System

Classical International Typographic Style: flat whites, blacks, a disciplined grid, and a decisive red signal.

## Overview

This system is built on three principles:
1. **Grid discipline** — 12 columns, consistent spacing, nothing free-floating.
2. **Typographic hierarchy** — Inter Tight for display/headings, Inter for body. Size and weight do the work; color does not.
3. **Single accent** — `#DC2626` (Tertiary) is the only color that signals action. One per screen, maximum.

---

## Color Tokens

| Token | Hex | Usage |
|---|---|---|
| `primary` | `#000000` | Headlines, core body text, primary UI text |
| `secondary` | `#555555` | Borders, captions, timestamps, metadata |
| `tertiary` | `#DC2626` | **One interactive action per screen only** |
| `neutral` | `#F5F5F5` | Page backgrounds, section fills |
| `surface` | `#FFFFFF` | Cards, modals, elevated content areas |
| `on-primary` | `#FFFFFF` | Text/icons on dark or tertiary backgrounds |

### Color Rules

- **Do** reserve Tertiary for exactly one primary CTA per screen.
- **Do** use Secondary for all supporting, non-interactive text and dividers.
- **Don't** introduce any additional accent or brand color.
- **Don't** use gradients. This system is flat.
- **Don't** tint or shade Tertiary — use it as-is or not at all.

---

## Typography Tokens

| Token | Family | Size | Weight | Tracking | Line Height |
|---|---|---|---|---|---|
| `display` | Inter Tight | 4rem | 700 | -0.03em | — |
| `h1` | Inter Tight | 2.25rem | 700 | -0.02em | — |
| `body` | Inter | 0.95rem | 400 | — | 1.55 |
| `label` | Inter | 0.75rem | 400 | 0.02em | — |

### Typography Rules

- Load both `Inter Tight` (weights 700) and `Inter` (weight 400, 500) from Google Fonts.
- Negative letter-spacing on display/h1 is intentional — do not remove it.
- Uppercase labels use `letter-spacing: 0.02em` to aid legibility at small sizes.
- Never use font-weight below 400 or above 700 in this system.

---

## Spacing Tokens

| Token | Value |
|---|---|
| `spacing.sm` | 8px |
| `spacing.md` | 16px |
| `spacing.lg` | 32px |

Derive all other spacing values as multiples: 4px, 8px, 16px, 24px, 32px, 48px, 64px.

---

## Border Radius

All components use `border-radius: 0px`. This is a deliberate design choice — do not add rounding.

---

## Component Specifications

### Button (Primary)

```
background: #DC2626       (tertiary)
color:      #FFFFFF       (on-primary)
border-radius: 0px
padding: 12px 20px
font: Inter, 0.95rem
```

- Only one primary button per screen.
- No hover gradients — change only opacity or darken background slightly (`#B91C1C`).
- Secondary actions use a text-only or outline variant (black border, transparent background).

### Card

```
background: #FFFFFF       (surface)
color:      #000000       (primary)
border-radius: 0px
padding: 24px
border: 1px solid #E5E5E5  (light neutral border for definition)
```

---

## Grid System

- **12-column grid**, `max-width: 1280px`, `margin: 0 auto`.
- Column gutters: `24px` (desktop), `16px` (tablet), `12px` (mobile).
- Use CSS Grid or a utility framework grid (e.g., Tailwind's `grid-cols-12`).
- Content lives inside the grid — no full-bleed elements unless they are background fills.

### Responsive Breakpoints

| Breakpoint | Width | Columns |
|---|---|---|
| Mobile | < 640px | 4 |
| Tablet | 640px – 1024px | 8 |
| Desktop | > 1024px | 12 |

---

## Implementation Checklist

When building any interface with this skill:

- [ ] Import Inter Tight (700) and Inter (400, 500) from Google Fonts.
- [ ] Define CSS custom properties or Tailwind config entries for all color and typography tokens.
- [ ] Use `border-radius: 0` globally.
- [ ] Apply a 12-column grid layout with correct gutters.
- [ ] Ensure exactly one Tertiary-colored CTA per screen/page.
- [ ] Use Neutral (`#F5F5F5`) as the page background — never pure white at page level.
- [ ] All text on colored backgrounds must meet WCAG AA contrast (4.5:1 minimum).
- [ ] No gradients, no shadows beyond subtle `box-shadow: 0 1px 3px rgba(0,0,0,0.08)` on cards.

---

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use Tertiary for one action per screen | Use Tertiary decoratively |
| Let negative space breathe | Fill every pixel |
| Use Secondary for borders and meta text | Use Primary for secondary content |
| Keep Inter Tight exclusively for headings | Mix heading and body typefaces arbitrarily |
| Use flat fills | Use gradients or patterns |
| Compose with the 12-column grid | Float elements outside the grid |
