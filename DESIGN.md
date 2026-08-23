---
name: FideliChem Scientific Console
description: A calm, auditable desktop workspace for evidence-backed chemistry decisions.
colors:
  canvas: "#0B1220"
  surface: "#111B2F"
  surface-raised: "#16243A"
  surface-input: "#0F192B"
  border: "#273750"
  border-strong: "#385170"
  text: "#EAF2FF"
  text-muted: "#95A7C2"
  accent: "#5BE6C7"
  accent-pressed: "#35B99D"
  accent-soft: "#173A3D"
  warning: "#FFCA7A"
  danger: "#FF7B88"
typography:
  brand:
    fontFamily: "Segoe UI, Inter, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.2
  caption:
    fontFamily: "Segoe UI, Inter, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.3
  headline:
    fontFamily: "Segoe UI, Inter, sans-serif"
    fontSize: "23px"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "Segoe UI, Inter, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Segoe UI, Inter, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "1px"
rounded:
  xs: "4px"
  sm: "8px"
  md: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "32px"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "32px"
  field:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 10px"
    height: "32px"
  navigation-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
---

# Design System: FideliChem Scientific Console

## Overview

**Creative North Star: "The Traceable Lab Console"**

FideliChem should feel like a well-kept instrument panel: quiet enough for
careful reading, structured enough to expose the state of evidence, and
deliberate about every action that can change a workspace. The interface uses
tonal layers instead of decorative effects, with one restrained accent reserved
for actions, focus, and trustworthy positive state.

Information density is intentional. Tables and evidence panes are allowed to
carry detail, but page headers, labels, and navigation establish a reliable
reading order. The system is dark-first for long analysis sessions and keeps
focus, disabled, warning, and error states visible without relying on color
alone.

**Key Characteristics:**

- Layered midnight surfaces with a cool, high-contrast text scale.
- Turquoise accent used sparingly for action and active state.
- Compact, rectangular controls with gently rounded corners.
- Explicit status language for workspace, import, QC, and export state.

## Colors

The palette is a cool midnight laboratory: dark surfaces reduce glare while
the single turquoise accent creates a clear action hierarchy.

### Primary

- **Signal Turquoise**: the primary action, focus, and active-navigation color.

### Neutral

- **Midnight Canvas**: the application background and deepest contrast field.
- **Instrument Surface**: navigation and status surfaces.
- **Raised Surface**: table headers, secondary controls, and selected layers.
- **Input Well**: editable and read-only evidence fields.
- **Paper Text**: primary content text.
- **Muted Slate**: labels, supporting copy, and inactive navigation.
- **Graphite Borders**: separators and low-noise structural edges.

### Named Rules

**The One Signal Rule.** The accent is reserved for an action, an active state,
or a focus ring; it is not a decorative fill.

## Typography

**Display Font:** Segoe UI (with Inter and sans-serif fallbacks)

**Body Font:** Segoe UI (with Inter and sans-serif fallbacks)

**Label/Mono Font:** Segoe UI for labels; scientific values keep their source
format and are never silently rounded in the data layer.

**Character:** Compact, neutral, and highly legible. Weight and spacing create
hierarchy rather than oversized display copy.

### Hierarchy

- **Headline** (700, 23px, 1.2): page titles and major analysis contexts.
- **Body** (400, 13px, 1.4): evidence, controls, and explanatory copy.
- **Label** (700, 11px, 1.2, tracked): section markers and navigation context.

### Named Rules

**The Evidence First Rule.** Use readable body text for scientific content;
labels may be compact, but evidence is never reduced to ornamental microcopy.

## Layout

The shell uses a fixed navigation rail and a flexible analysis canvas. Outer
padding is 16px, the rail is 208px wide, and panels use a 12px internal rhythm.
Split views keep related evidence visible together and allow tables to expand
without competing with the navigation. At smaller widths, the canvas remains
usable through Qt's native layout compression rather than clipped fixed panels.

## Elevation & Depth

Depth is conveyed through tonal layering and borders, not shadows or gradients.
The canvas is deepest, workspace surfaces sit one step above it, and raised
surfaces are reserved for controls, headers, and selected state.

### Named Rules

**The Flat-by-Default Rule.** A surface is flat at rest; state changes are
communicated by a border, tonal shift, or explicit status label.

## Shapes

Controls and panels use gently rounded 8px corners. The navigation rail is the
one larger 14px silhouette, acting as a stable instrument housing. Borders are
thin and structural; there are no pill-shaped controls except compact status
badges where the contained text is genuinely a state.

## Components

### Buttons

- **Shape:** gently rounded corners (8px).
- **Primary:** turquoise action fill with dark text and compact 32px height.
- **Hover / Focus:** accent darkens on hover; focus keeps a visible accent edge.
- **Secondary:** raised surface with a structural border; hover promotes the
  border and text to the accent.

### Cards / Containers

- **Corner Style:** 8px for content surfaces, 14px for the navigation rail.
- **Background:** canvas, instrument surface, and raised surface layers.
- **Shadow Strategy:** no shadows; use tonal layering and borders.
- **Border:** graphite structural edge, promoted only for focus/active state.
- **Internal Padding:** 8px, 12px, or 16px according to content density.

### Inputs / Fields

- **Style:** dark input well, 1px border, 8px radius, 32px minimum height.
- **Focus:** accent border visible against the input well.
- **Error / Disabled:** disabled controls mute text and return to the surface
  layer; error and warning copy must remain explicit in the surrounding state.

### Navigation

- **Style:** compact vertical list in the instrument rail.
- **Default / Hover:** muted label becomes readable on a raised surface.
- **Active:** accent-soft background and turquoise label; the selected row is
  always visible without relying on position alone.

## Do's and Don'ts

### Do:

- **Do** keep one shared stylesheet and token vocabulary for every view.
- **Do** expose loading, empty, disabled, warning, and error states in text.
- **Do** preserve native keyboard focus and accessible names on inputs.
- **Do** use the accent only where a user action or active evidence state needs it.

### Don't:

- **Don't** add gradients, glassmorphism, decorative shadows, or noisy background
  art to analysis surfaces.
- **Don't** hide missing scientific evidence by replacing it with zero or a
  reassuring-looking placeholder.
- **Don't** put scientific rules or persistence calls inside view widgets.
