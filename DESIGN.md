```markdown
# Design System Strategy: HostCheck Technical Interface

## 1. Overview & Creative North Star: "Atmospheric Precision"
This design system moves beyond the "SaaS template" by embracing a philosophy of **Atmospheric Precision**. In the world of high-stakes hosting and infrastructure, the UI must feel like a high-performance cockpit—authoritative, calm, and deeply organized.

We break the standard grid through **Intentional Asymmetry**. Instead of centering everything, we lean into editorial layouts where information density is balanced by vast negative space. The "Linear" or "Vercel" aesthetic is achieved not by copying their components, but by mimicking their restraint. We treat the screen as a dark void where light (color) and depth (layering) are used sparingly to guide the eye to critical system statuses.

## 2. Color & Surface Architecture
The palette is rooted in deep obsidian tones, utilizing the Material Design naming convention to create a sophisticated, multi-layered environment.

### The "No-Line" Rule
To achieve a premium editorial feel, **1px solid borders are prohibited for sectioning.** Traditional boxes make a UI feel "boxed in." Instead, boundaries must be defined by:
*   **Tonal Shifts:** Placing a `surface-container-low` (#1a1c20) card against a `surface` (#111317) background.
*   **Physical Distance:** Using the Spacing Scale to create "islands" of information.

### Surface Hierarchy & Nesting
Treat the UI as a series of nested, physical layers. 
*   **Base:** `surface` (#111317) for the main application background.
*   **Sections:** Use `surface-container-low` (#1a1c20) to define larger working areas.
*   **Interactive Elements:** Use `surface-container-high` (#282a2e) for cards or panels that require user focus.
*   **The Layering Principle:** Always nest "up." A `surface-container-highest` (#333539) element should only sit inside a `surface-container-high` or `low` area, creating a natural, logical lift.

### The "Glass & Gradient" Rule
For floating elements like Command Palettes or Tooltips, utilize **Glassmorphism**. Combine `surface-container-highest` at 80% opacity with a `backdrop-blur` (20px-40px). 
*   **Signature Textures:** Main CTAs should not be flat blue. Use a subtle linear gradient from `primary` (#adc6ff) to `primary_container` (#4d8eff) at a 135-degree angle to provide a "lit from within" soul to the interface.

## 3. Typography: Editorial Authority
We use **Inter** as our typographic backbone. The goal is high-contrast information density.

*   **Display & Headlines:** Use `display-md` (2.75rem) for high-level system health or hero metrics. These should have a slight negative letter-spacing (-0.02em) to feel tighter and more custom.
*   **The Label Strategy:** Technical data (IP addresses, server logs, timestamps) must use `label-md` or `label-sm` in `on_surface_variant` (#c2c6d6). This creates a clear distinction between "Interface Narrative" (Headlines) and "System Data" (Labels).
*   **Body:** `body-md` (0.875rem) is the workhorse. Keep line heights generous (1.5) to maintain readability against the dark background.

## 4. Elevation & Depth
In a dark theme, shadows behave differently. They represent "ambient occlusion" rather than direct sunlight.

*   **Ambient Shadows:** For floating panels, use a large blur (32px to 64px) with a 4-8% opacity. The shadow color should be a deep navy-tinted black rather than pure grey to harmonize with our `primary` tones.
*   **The "Ghost Border" Fallback:** If a container lacks sufficient contrast against its neighbor, apply a Ghost Border. This is an `outline-variant` (#424754) border set to **15% opacity**. It provides a "whisper" of an edge that disappears into the background.
*   **Tonal Layering:** Avoid "Drop Shadows" for standard cards. Use the transition from `surface-container-lowest` to `surface-container-low` to imply depth.

## 5. Components

### Buttons
*   **Primary:** Gradient of `primary` to `primary_container`. `md` (0.375rem) corner radius. Use `on_primary` (#002e6a) for text to ensure high-contrast legibility.
*   **Secondary:** `surface-container-highest` background with a Ghost Border.
*   **States:** On hover, primary buttons should emit a subtle outer glow (0px 0px 12px) using the `primary` color at 30% opacity.

### Input Fields
*   **Styling:** Background of `surface-container-lowest`. No border.
*   **Focus State:** A 1px Ghost Border (at 40% opacity) and a subtle 2px inner-shadow to give the field a "recessed" feel.

### Status Indicators (High-Contrast)
*   **Critical (Error):** `error` (#ffb4ab).
*   **Warning (Tertiary):** `tertiary` (#ffb786).
*   **Healthy (Secondary):** `secondary` (#b1c6f9).
*   **Design Note:** Use these colors for small, high-intensity elements (dots, thin status bars, or icons) against the dark `surface-variant`.

### Cards & Lists
*   **No Dividers:** Prohibit the use of horizontal rules (`<hr>`). Separate list items using a 4px gap and a background shift to `surface-container-low` on hover. 
*   **Asymmetric Data:** In server lists, align primary identifiers (Server Name) to the left using `title-md`, and technical metadata (Latency, Uptime) to the right using `label-sm` for an editorial look.

### HostCheck Specific Components: "The Pulse"
*   **Live Log Stream:** Use `surface-container-lowest` for the container. Use `on_surface_variant` for the text. Use a `primary` (#adc6ff) 2px vertical "glow bar" on the left of the active log line to show real-time movement.

## 6. Do's and Don'ts

### Do:
*   **Do** use "Optical Alignment." Sometimes a button needs to be 1px higher to *look* centered. Trust your eyes over the grid.
*   **Do** use `primary_fixed_dim` for icons to keep them from "vibrating" against the dark background.
*   **Do** embrace negative space. If a page feels crowded, increase the padding between `surface-container` tiers.

### Don't:
*   **Don't** use pure #000000 or pure #FFFFFF. Use our `surface` and `on_surface` tokens to maintain tonal depth.
*   **Don't** use standard "heavy" shadows. If you can see the shadow clearly, it’s too dark.
*   **Don't** use borders to separate the sidebar from the main content. Use a background shift from `surface-container-low` (Sidebar) to `surface` (Main).

---
*Director's Final Note: Precision is not the absence of complexity, but the mastery of it. Keep the HostCheck interface feeling light, fast, and intentional.*```