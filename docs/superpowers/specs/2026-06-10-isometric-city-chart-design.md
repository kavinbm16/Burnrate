# IsometricCityChart — Design Spec

**Date:** 2026-06-10  
**Project:** Burnrate / machanirobotics/token-usage  
**Status:** Approved

---

## Overview

A canvas-based 3D isometric city visualization added as a hero section below the existing stat cards on the Analytics page. Each "building" represents one benchmark session; building height encodes total cost in USD; color encodes config type. Sessions are arranged chronologically left-to-right.

---

## Placement

`AnalyticsView.svelte` layout (top to bottom):

1. Existing 3-card stat row (unchanged)
2. **`<IsometricCityChart>` — new hero card** ← inserted here
3. Insight cards
4. Cost-per-hour bar chart
5. Projection panel
6. Sessions table

---

## Component

**File:** `frontend/src/lib/components/IsometricCityChart.svelte`

### Props

```ts
sessions: Session[]          // from app.sessions
onDrilldown: (id: string) => void  // fires app.drilldownSessionId = id
```

### Internal structure

- Single `<canvas>` element, width = container width (ResizeObserver), height = 240px fixed
- A `<div>` stat footer bar below the canvas showing: Sessions · Total spend · Peak session · Avg/session
- No external dependencies — pure canvas 2D context

---

## Canvas Rendering

### Projection

Cabinet oblique projection (matches approved mockup):

```
Constants:
  bw  = 30   // building front face width (px)
  bd  = 18   // depth x-offset for top/right faces
  bdh = 9    // depth y-offset for top/right faces
  slot_w = 48  // px per building slot (includes gap)
  MAX_BH = 130 // max building height (px) for highest-cost session
  baseline_y = canvas.height - 35  // ground line, leaves room for date labels
  origin_x = 42
```

For building `i` at `x = origin_x + i * slot_w`, `bh = (session.total_cost_usd / maxCost) * MAX_BH`:

- **Front face** (rectangle): `(x, baseline-bh) → (x+bw, baseline-bh) → (x+bw, baseline) → (x, baseline)`
- **Top face** (parallelogram): `(x, baseline-bh) → (x+bw, baseline-bh) → (x+bw+bd, baseline-bh-bdh) → (x+bd, baseline-bh-bdh)`
- **Right face** (parallelogram): `(x+bw, baseline-bh) → (x+bw, baseline) → (x+bw+bd, baseline-bdh) → (x+bw+bd, baseline-bh-bdh)`
- **Base shadow strip**: bottom 3px of front face filled with `rgba(0,0,0,0.25)`

### Color map

| Config | Front | Top | Right |
|--------|-------|-----|-------|
| baseline (no tools, no headroom) | `#d97706` | `#fbbf24` | `#92400e` |
| tools only | `#ea580c` | `#fb923c` | `#7c2d12` |
| headroom only | `#dc2626` | `#f87171` | `#7f1d1d` |
| full (tools + headroom) | `#db2777` | `#f472b6` | `#9d174d` |

Config derived from `session.tools_enabled` and `session.headroom_enabled`.

### Ground plane

Parallelogram from `(origin_x, baseline)` to `(last_x + bw, baseline)` to `(last_x + bw + bd, baseline - bdh)` to `(origin_x + bd, baseline - bdh)`. Dark fill with subtle grid slot divider lines.

### Y-axis

Three horizontal reference lines with cost labels (`$0.05`, `$0.10`, `$0.15`) at corresponding y positions left of `origin_x`. Single vertical axis line.

### Date labels

Below each building slot at `baseline + 18px`. Format: `MMM D` from `session.created_at`.

---

## Entrance Animation

On mount, each building animates from `bh = 0` to its target height:

- Duration per building: 300ms ease-out
- Stagger: 40ms per building index
- Implemented with `requestAnimationFrame` loop tracking elapsed time per building
- Canvas redraws every frame during animation

---

## Interactions

### Hover

`mousemove` event on the canvas element:

1. Hit-test: check if pointer x,y falls within each building's front-face bounding rect `(x, baseline-bh, bw, bh)`
2. On match: redraw hovered building with `ctx.shadowBlur = 12`, `ctx.shadowColor = top_color`, and 1px bright outline around all three faces
3. Draw tooltip (see below)
4. Cursor: `pointer`

`mouseleave`: clear hover state, redraw without highlight

### Tooltip (drawn on canvas)

Rendered as canvas fillRect + fillText, no DOM overlay:

```
┌─────────────────────────┐
│ scenario_name           │  ← white bold 10px
│ config label            │  ← config color 9px
│ Cost $X.XX  · Xm XXs    │  ← muted 9px
│ ↑ XX.Xk tok  ↓ XX.Xk   │  ← muted 9px
└─────────────────────────┘
```

- Width: 160px, height: 72px, rounded rect (r=5)
- Background: `#0f172a`, border: config front color, 1px
- Positioned above+right of hovered building; clamps to canvas bounds
- Dashed connector line from tooltip bottom to building top-center

### Click

`click` event: if a building is hovered at click time, call `onDrilldown(session.id)`.

---

## Empty State

When `sessions.length < 2`:

- Draw 5 ghost building outlines (dashed stroke, `#1e293b`) at random heights
- Centered text: `"Run a sim session to populate the city"` in `#334155`

---

## Stat Footer Bar

Below the canvas, inside the card:

```
Sessions  |  Total spend  |  Peak session  |  Avg / session
   10     |    $0.64      |     $0.15      |     $0.064
```

Derived directly from the `sessions` prop — no additional API calls.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/lib/components/IsometricCityChart.svelte` | **New** — canvas component |
| `frontend/src/lib/views/AnalyticsView.svelte` | Import and insert `<IsometricCityChart>` below stat cards row |
