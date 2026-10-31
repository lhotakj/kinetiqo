---
name: web-elements
description: Authoritative styling guidelines, Tailwind CSS classes, color schemes, geometry, and accessible HTML patterns for GUI elements (buttons, inputs, dropdowns, panels, and sidebars) across the Kinetiqo dashboard.
---

# Kinetiqo Web GUI Elements & Styling Standards

This skill defines the authoritative design tokens, Tailwind CSS utility classes, layout geometries, and accessible markup patterns for all GUI components across the Kinetiqo web application.

---

## 1. Action Buttons (`/activities` Grid Toolbar & Triggers)

Buttons in Kinetiqo are categorized into primary semantic actions, secondary utility triggers, and async export triggers.

### 1.1 Geometry & Sizing Standards
- **Height**: Fixed `h-[40px]` (`min-height: 40px` / `2.5rem`) across all toolbar and action buttons to ensure pixel-perfect vertical alignment with inputs and dropdowns.
- **Padding**: Standard action button padding is `px-3 py-2` (horizontal 12px, vertical 8px). Primary standalone CTAs may use `px-4 py-2`.
- **Border Radius**: Use `rounded` (`border-radius: 0.25rem` / 4px) for grid action buttons; use `rounded-lg` (8px) for isolated action pills or modal triggers.
- **Typography**: `text-sm font-small` (or `font-medium`), clean baseline alignment. Button text must be wrapped inside a `<span>` element immediately following the icon.
- **Layout**: Always enforce `flex items-center` or `inline-flex items-center` to guarantee vertical centering of SVG icons and text labels.
- **Transitions**: Include `transition` (or `transition-colors duration-150`) for smooth hover feedback.

### 1.2 Semantic Color Palette
Kinetiqo adheres to a strict semantic color system:

| Role / Intent | Active State Classes | Hover State Classes | Disabled State Classes | Example Use in Kinetiqo |
|---|---|---|---|---|
| **Destructive / Delete** | `bg-red-500 text-white` | `hover:bg-red-600` | `bg-gray-400 text-white` | `#deleteSelectedBtn` |
| **Accent / Map** | `bg-orange-500 text-white` | `hover:bg-orange-600` | `bg-gray-400 text-white` | `#displayOnMapBtn` |
| **Analytics / Power** | `bg-purple-600 text-white` | `hover:bg-purple-700` | `bg-gray-400 text-white` | `#powerSkillsBtn` |
| **AI Operations** | `bg-teal-600 text-white` | `hover:bg-teal-700` | `bg-gray-400 text-white` | `#purgeAiBtn` |
| **CSV / Data Export** | `bg-blue-600 text-white` | `hover:bg-blue-700` | `bg-gray-400 text-white` | `#exportCsvBtn`, `#btn-download-png` |
| **Spreadsheet / Success** | `bg-green-600 text-white` | `hover:bg-green-700` | `bg-gray-400 text-white` | `#exportXlsxBtn`, `#btn-download-pdf` |
| **Warning / Reset** | `bg-yellow-500 text-white` | `hover:bg-yellow-600` | `bg-gray-400 text-white` | `#resetViewBtn` |
| **Neutral Utility** | `bg-gray-500 text-white` | `hover:bg-gray-600` | `bg-gray-400 text-white` | `#selectColumnsBtn` |
| **Secondary / Toggles** | `bg-gray-100 text-gray-700` | `hover:bg-gray-200` | `bg-gray-200 text-gray-400` | `#selectAllBtn`, `#deselectAllBtn` |

### 1.3 SVG Icon Guidelines
- **Dimensions**: Strictly `w-4 h-4 mr-2` (16px × 16px with an 8px right margin).
- **Stroke & Fill**: Stroke-only icons inheriting `currentColor`:
  - `fill="none"`
  - `stroke="currentColor"`
  - `viewBox="0 0 24 24"`
  - `stroke-width="1.5"` or `"2"`
  - `stroke-linecap="round"`
  - `stroke-linejoin="round"`
  - `aria-hidden="true"`

### 1.4 Dynamic Button State Management (JavaScript)
Action buttons tied to selection states (e.g. DataTables rows) are dynamically enabled or disabled using helper routines:

```javascript
function setButtonState(selector, isEnabled, activeClass, disabledClass) {
    const $btn = $(selector);
    $btn.prop('disabled', !isEnabled);
    if (isEnabled) {
        $btn.removeClass(disabledClass).addClass(activeClass);
    } else {
        $btn.removeClass(activeClass).addClass(disabledClass);
    }
}

// Example usage:
setButtonState('#purgeAiBtn', hasSelection, 'bg-teal-600 hover:bg-teal-700', 'bg-gray-400');
setButtonState('#deleteSelectedBtn', hasSelection, 'bg-red-500 hover:bg-red-600', 'bg-gray-400');
```

### 1.5 Waiting States (ui-loading-standards)
When an action button performs an asynchronous operation (e.g. PDF/PNG generation or sync):
- **Never display accompanying text** (e.g. `"Exporting..."` or `"Uploading..."`).
- Replace button contents entirely with `static/img/kinetiqo-loading-32x32.webp` (`16x16` or `20x20` px).
- Set `btn.disabled = true;` and apply `opacity-60 cursor-wait`.
- Store `origHtml = btn.innerHTML;` and restore it inside a `finally` block.

### 1.6 Compliant Action Button HTML Examples
```html
<!-- Primary Action Button (AI Purge) -->
<button id="purgeAiBtn"
        class="px-3 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded text-sm font-small transition h-[40px] flex items-center"
        title="Purge cached AI analysis">
    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
    </svg>
    <span>Purge AI analysis</span>
</button>

<!-- Secondary Neutral Action Button -->
<button id="selectAllBtn"
        class="px-3 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-sm font-small transition h-[40px] flex items-center"
        title="Select all activity types">
    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
    </svg>
    <span>Select All</span>
</button>
```

---

## 2. Text Inputs & Textareas (`/settings` Inputs & Templates)

Text boxes and textareas are used for configurations, API identifiers, numeric metrics (FTP, weight), and multi-line template text.

### 2.1 Geometry & Padding
- **Standard Single-Line Input**: Height `min-height: 40px` or `42px` (`h-[40px]` or `p-2.5` / `px-3 py-2`).
- **Corner Radius**: `rounded-lg` (8px) for forms and settings; `rounded` (4px) for dense data table filters.
- **Multi-Line Textareas**: Minimum height `min-h-[72px]` to `min-h-[96px]`, with `px-3 py-2 text-sm leading-relaxed`.

### 2.2 Typography: Standard vs Monospace
- **Standard Text**: Use `font-sans text-sm` (`text-gray-900 dark:text-gray-100`) for human-readable labels, prompt instructions, and general search.
- **Monospace Code/Identifiers**: Use `font-mono text-xs` (or `font-mono text-sm`) for:
  - AI model identifiers (e.g. `kilo-auto/free`, `google/gemini-2.5-flash`).
  - Strava description update templates (`UPDATE_STRAVA_*`).
  - Regex patterns and API credentials.

### 2.3 Theme Skinning (Light vs Dark Mode)
Always support dual-theme skinning with clean contrast:

| Attribute | Light Mode Classes | Dark Mode Classes |
|---|---|---|
| **Background** | `bg-white` or `bg-gray-50` | `dark:bg-zinc-900` or `dark:bg-zinc-800` |
| **Border** | `border border-gray-300` or `border-warm-200` | `dark:border-zinc-700` or `dark:border-zinc-600` |
| **Text Color** | `text-gray-900` or `text-gray-800` | `dark:text-white` or `dark:text-gray-200` |
| **Placeholder** | `placeholder-gray-400` | `dark:placeholder-zinc-500` |
| **Focus State** | `focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500` (or `focus:ring-orange-500`) | `dark:focus:bg-zinc-800 dark:focus:ring-blue-500` |

### 2.4 Label Accessibility & Form Association (Sonar Web:S6853)
- Every `<input>` and `<textarea>` **must** have an associated `<label for="id">` matching its `id`, or an explicit `aria-label`.
- Form headers must align the label and real-time status indicator using flexbox:
  ```html
  <div class="flex items-center justify-between mb-1">
      <label for="model-id" class="text-xs font-medium text-gray-700 dark:text-gray-300">
          Model Identifier
      </label>
      <span id="model-id-status" class="text-xs font-medium"></span>
  </div>
  ```

### 2.5 Validation & Error Highlighting Standard
In accordance with Kinetiqo's input validation rules:
- **Normal State**: `bg-white dark:bg-zinc-900 border-gray-300 dark:border-zinc-600`.
- **Validation Failure**: The input background highlights in a light red tone:
  `bg-red-50 dark:bg-red-950/40 border-red-400 dark:border-red-600 text-red-900 dark:text-red-200`.
  Validation error text appears adjacent to the label in red.
- **Success State**: Input reverts to normal, and a green **`Saved ✓`** tag appears adjacent to the label, fading automatically after 3 seconds.

### 2.6 Compliant Input Code Example
```html
<div class="space-y-1.5">
    <div class="flex items-center justify-between">
        <label for="kilo-new-model-id" class="text-xs font-medium text-gray-700 dark:text-gray-300">
            Model Identifier
        </label>
        <span id="kilo-new-model-status" class="text-xs font-medium"></span>
    </div>
    <div class="flex items-center gap-2">
        <input id="kilo-new-model-id"
               type="text"
               autocomplete="off"
               aria-label="Kilo AI Gateway Model Identifier"
               class="w-full rounded-lg border border-gray-300 bg-gray-50 dark:bg-zinc-900 p-2.5 text-xs font-mono text-gray-900 dark:border-zinc-600 dark:text-white focus:bg-white dark:focus:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-orange-500 transition"
               placeholder="e.g. kilo-auto/free">
        <button id="kilo-add-model-btn"
                type="button"
                class="min-h-10 inline-flex items-center gap-1.5 rounded-lg bg-orange-500 px-4 py-2 text-xs font-medium text-white hover:bg-orange-600 transition shadow-xs cursor-pointer"
                title="Validate and add model">
            <span>Add</span>
        </button>
    </div>
</div>
```

---

## 3. Dropdowns & Emulated Select Inputs (`/chat` Model Selector)

Custom dropdowns are used when standard HTML `<select>` elements cannot display rich metadata, such as provider brand icons, default badges, model latency indicators, or styled scrollbars.

### 3.1 Trigger Button Anatomy (Input Emulation)
The trigger element visually mirrors a standard text input box:
- **Geometry**: `min-height: 36px` to `40px`, `padding: 8px 11px`, `border-radius: 8px`.
- **Borders & Background**:
  - Light mode: `border: 1px solid #e5e7eb; background: #ffffff; color: #374151;`.
  - Dark mode: `border: 1px solid #3f3f46; background: #27272a; color: #f4f4f5;`.
- **Typography**: `font-size: 12px; font-weight: 500;`.
- **Truncation**: The label container must enforce ellipsis so long names do not push out the trailing chevron:
  `flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left;`.
- **Trailing Icons**: Flex container (`gap: 6px; margin-left: auto;`) housing optional badges (e.g. gold star for default) and a downward chevron SVG (`w-3.5 h-3.5`).

### 3.2 Custom Provider & Group Icons
- **Icon Sizing**: `14px × 14px` (`w-3.5 h-3.5`), `object-fit: contain; flex-shrink: 0;`.
- **Monochrome Theme Adaptation**:
  Monochrome provider SVGs (such as OpenAI, Anthropic, Gemini, Kilo) use CSS filters to automatically match theme contrast:
  ```css
  /* Light mode: dark charcoal tint */
  .chat-model-group-icon,
  #chat-model-trigger-icon {
      filter: brightness(0) invert(28%);
      transition: filter 0.15s ease-in-out;
  }

  /* Dark mode: crisp off-white tint */
  html.dark .chat-model-group-icon,
  html.dark #chat-model-trigger-icon {
      filter: brightness(0) invert(85%);
  }

  /* Invert solid black vendor marks */
  html.dark .chat-model-group-icon[data-provider="kilo"],
  html.dark .chat-model-group-icon[data-provider="vercel"] {
      filter: invert(1);
  }
  ```

### 3.3 Floating Menu Container & Elevation Standard
- **Positioning & z-index**: `position: absolute; width: 100%; max-height: 320px; overflow-y: auto; z-index: 100;` (`z-[100]`).
- **Container Stacking Context**: The relative trigger container (`.relative`) should define a default stacking tier (`z-30`) and dynamically elevate to `z-50` on menu open. This prevents sibling DOM elements or descriptions below the input from painting over the floating menu.
- **Shadows & Elevation**:
  - Light: `background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1);`.
  - Dark: `background: #27272a; border: 1px solid #3f3f46; border-radius: 8px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.45), 0 8px 10px -6px rgba(0,0,0,0.45);`.
- **Group Headers**: `font-size: 11px; font-weight: 700; color: #6b7280; dark:color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.02em; padding: 4px 8px;`.
- **Option Items (`.chat-model-item` / `.strava-var-item`)**:
  - Base: `width: 100%; padding: 7px 8px; border-radius: 6px; font-size: 12px; display: inline-flex; items-center; justify-content: space-between; cursor: pointer;`.
  - Light Hover: `hover:bg-gray-100 text-gray-900`.
  - Dark Hover: `dark:hover:bg-zinc-700 dark:text-zinc-200`.
  - Selected Item: Light `bg-blue-50 text-blue-700 font-semibold` (or `bg-orange-50 text-orange-700`); Dark `bg-blue-950/40 text-blue-300 font-semibold`.

### 3.4 Custom Scrollbar Styling
Custom dropdown menus must render clean, unobtrusive scrollbars across all modern rendering engines:

```css
/* Firefox Standard */
.chat-model-menu {
    scrollbar-width: thin;
    scrollbar-color: #d1d5db transparent;
}
html.dark .chat-model-menu {
    scrollbar-color: #52525b transparent;
}

/* WebKit / Chromium Browsers */
.chat-model-menu::-webkit-scrollbar {
    width: 6px;
}
.chat-model-menu::-webkit-scrollbar-thumb {
    background: #d1d5db;
    border-radius: 9999px;
}
html.dark .chat-model-menu::-webkit-scrollbar-thumb {
    background: #52525b;
}
.chat-model-menu::-webkit-scrollbar-track {
    background: transparent;
}
```

### 3.5 Compliant Dropdown HTML Example
```html
<div class="relative w-full max-w-sm">
    <label for="ai-model-select" class="sr-only">Select Model</label>
    <select id="ai-model-select" class="sr-only" tabindex="-1">
        <option value="gemini-2.5-flash" selected>gemini-2.5-flash</option>
    </select>

    <!-- Trigger Box -->
    <button id="ai-model-trigger"
            type="button"
            class="w-full min-h-[38px] px-3 py-2 bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-lg text-xs font-medium text-gray-800 dark:text-zinc-200 flex items-center justify-between gap-2 shadow-xs hover:bg-gray-50 dark:hover:bg-zinc-700/60 focus:outline-none focus:ring-2 focus:ring-orange-500 transition"
            aria-haspopup="listbox"
            aria-expanded="false">
        <img src="/static/icons/ai_gemini.svg" alt="" class="w-3.5 h-3.5 object-contain shrink-0" aria-hidden="true">
        <span class="flex-1 text-left truncate">gemini-2.5-flash</span>
        <svg class="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7" />
        </svg>
    </button>

    <!-- Popover Menu -->
    <div id="ai-model-menu"
         class="hidden absolute bottom-full mb-1 left-0 w-full max-h-64 overflow-y-auto bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-lg shadow-xl p-1.5 z-60"
         role="listbox">
        <!-- Group & Items populated dynamically -->
    </div>
</div>
```

---

## 4. Headerless Panels (`/activities` Filter Pane)

Headerless panels are flat container cards designed for compact controls, multi-input filter strips, or dashboard data summaries where a dedicated header bar would consume excessive vertical space.

### 4.1 Visual Hierarchy & Tokens
- **Container**: Flat, padded card with full perimeter border and subtle drop shadow.
- **Background**:
  - Light mode: `bg-white`
  - Dark mode: `dark:bg-zinc-800`
- **Border**: `border border-gray-200 dark:border-zinc-700`.
- **Corner Radius**: `rounded-lg` (8px) or `rounded-xl` (12px).
- **Padding**: Uniform `p-4` (16px) or `p-5` (20px).
- **Separation**: Margin bottom `mb-4` or `mb-6`.

### 4.2 Grid & Layout Structure
Headerless filter panels typically use a 2-tier internal layout:
1. **Inputs Tier**: Responsive flex row (`flex flex-col md:flex-row gap-4 items-end`) ensuring labels, search fields, date selectors, and filter presets align along their bottom edge.
2. **Action Toolbar Tier**: Full-width bottom row (`w-full mt-4 flex justify-between items-center flex-wrap gap-4`) hosting selection toggles, batch action buttons, and table utility controls.

### 4.3 Compliant Headerless Panel HTML Example
```html
<div class="bg-white dark:bg-zinc-800 rounded-lg p-4 mb-4 border border-gray-200 dark:border-zinc-700 shadow-xs">
    <!-- Top Row: Form Controls -->
    <div class="flex flex-col md:flex-row gap-4 items-end">
        <div class="w-full md:w-64">
            <label for="customSearch" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Filter activities
            </label>
            <input type="text"
                   id="customSearch"
                   placeholder="Search by name..."
                   class="w-full px-3 py-2 border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded-lg focus:outline-none focus:ring-1 focus:ring-gray-300 text-sm h-[40px]">
        </div>
        <div class="w-full md:w-64">
            <label for="activityTypeFilter" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Activity Types
            </label>
            <select id="activityTypeFilter" class="w-full h-[40px] px-3 py-2 border border-gray-200 dark:border-zinc-700 rounded-lg bg-white dark:bg-zinc-900 text-sm">
                <option value="All">All Activities</option>
            </select>
        </div>
        <div class="flex-grow"></div>
        <div class="flex gap-2 items-center">
            <button class="px-3 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-sm h-[40px] flex items-center">
                <span>Reset Filters</span>
            </button>
        </div>
    </div>

    <!-- Bottom Row: Batch Actions Toolbar -->
    <div class="w-full mt-4 pt-3 border-t border-gray-100 dark:border-zinc-700/60 flex justify-between items-center flex-wrap gap-3">
        <div class="flex gap-2 items-center flex-wrap">
            <!-- Action buttons here -->
        </div>
    </div>
</div>
```

---

## 5. Headered Panels (`/settings` Configuration Cards)

Headered panels are high-prominence cards used for major configuration sections (e.g. Strava Description Templates, Athlete Profile & Heart Rate Zones, AI Provider Engine).

### 5.1 Card Structure & Outer Shell
- **Shell**: `bg-white dark:bg-zinc-800 rounded-xl shadow-sm border border-warm-200 dark:border-zinc-700 relative mb-6`.
- **Clipping & Dropdown Isolation**: Cards hosting floating custom dropdowns, comboboxes, or popovers must use `relative` without `overflow-hidden` to avoid clipping menus that extend below the card boundaries. The header banner enforces `rounded-t-xl` to maintain clean visual corner curvature.

### 5.2 Header Banner Anatomy & Monochromatic Header Icons
- **Background Tone**:
  - Light mode: Warm neutral `#9b9898` / `bg-warm-50` (or `bg-gray-50/90`).
  - Dark mode: Deep slate / dark blue-zinc `dark:bg-zinc-900`.
- **Padding & Divider**: `p-6 border-b border-warm-200 dark:border-zinc-700 rounded-t-xl`.
- **Strict Monochromatic Header Icons (No Background Box)**:
  - Header icons MUST be simple, monochromatic stroke-only SVGs placed directly inside the `<h2>` heading preceding the title text.
  - **Never use colored squares, rounded pills, or background containers** (e.g. do NOT use `<span class="inline-flex h-9 w-9 bg-gray-100...">`).
  - Icon styling: `h-5 w-5 shrink-0 text-gray-700 dark:text-gray-300`, stroke width `1.8`, `stroke-linecap="round"`, `stroke-linejoin="round"`.
- **Title**: `<h2 class="flex items-center gap-2.5 text-lg font-medium text-warm-900 dark:text-gray-100"><svg ...><span>Title Text</span></h2>`.
- **Subtitle / Description**: `text-sm text-gray-500 dark:text-gray-400 mt-1`.

### 5.3 Body Section
- **Padding**: `p-6 space-y-4` (or `p-6 space-y-6` for larger forms).

### 5.4 Compliant Headered Panel HTML Example
```html
<div id="templates" class="bg-white dark:bg-zinc-800 rounded-xl shadow-sm border border-warm-200 dark:border-zinc-700 relative mb-6">
    <!-- Header Banner -->
    <div class="p-6 border-b border-warm-200 dark:border-zinc-700 bg-warm-50 dark:bg-zinc-900 rounded-t-xl">
        <h2 class="flex items-center gap-2.5 text-lg font-medium text-warm-900 dark:text-gray-100">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 shrink-0 text-gray-700 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M8 4h8l4 4v12H4V4h4Z" /><path d="M16 4v5h4M8 13h8M8 17h6" />
            </svg>
            <span>Strava Description Templates</span>
        </h2>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Configure auto-update templates per activity type. Changes save automatically on blur.
        </p>
    </div>

    <!-- Panel Body -->
    <div class="p-6 space-y-4">
        <!-- Settings inputs, controls, or nested sub-panels -->
    </div>
</div>
```

---

## 6. Nested Panels (`/settings` Kinetiqo Agent Sub-Cards)

Nested panels represent sub-features or distinct sub-modules enclosed inside a parent headered card (e.g. the "Kinetiqo Agent" engine inside the Description Templates card).

### 6.1 Visual Hierarchy & Separation
To stand out clearly from the parent panel without adding visual clutter:
- **Card Shell**: `mt-4 p-4 rounded-xl bg-warm-50/80 dark:bg-zinc-900/80 border border-warm-200 dark:border-zinc-700 shadow-xs space-y-3 relative transition-all`.
- **Background Tone**:
  - Light mode: Slightly shaded warm/neutral fill (`bg-warm-50/80` or `bg-gray-50/80`).
  - Dark mode: Deep zinc backdrop (`dark:bg-zinc-900/80`).

### 6.2 Header with Toggle Switch & Icon
- **Header Row**: `flex flex-wrap items-center justify-between gap-2`.
- **Icon + Title**:
  - Icon: SVG glyph `h-5 w-5 shrink-0 text-gray-800 dark:text-gray-200`.
  - Title: `text-sm font-semibold text-gray-800 dark:text-gray-200`.
- **Checkbox Toggle**: Checkbox labeled with accessible markup:
  `rounded border-gray-300 dark:border-zinc-600 text-amber-600 focus:ring-amber-500`.

### 6.3 Variable Pills & Badges
Tokens and placeholder pills (e.g. `{{ai-agent}}`) embedded in nested panels use monospace badge pills:
`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border border-amber-300 dark:border-amber-800`.

### 6.4 Disabled / Inactive State
When a nested sub-feature is toggled off:
- Add `opacity-60 pointer-events-none select-none transition-opacity duration-200`.
- Form inputs inside become disabled.

### 6.5 Compliant Nested Panel HTML Example
```html
<div id="kinetiqo-agent-box"
     class="mt-4 p-4 rounded-xl bg-warm-50/80 dark:bg-zinc-900/80 border border-warm-200 dark:border-zinc-700 shadow-xs space-y-3 relative transition-all">
    <!-- Sub-Header Row -->
    <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 shrink-0 text-gray-800 dark:text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 8V4H8" />
                <rect width="16" height="12" x="4" y="8" rx="2" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M2 14h2M20 14h2M15 13v2M9 13v2" />
            </svg>
            <h4 class="text-sm font-semibold text-gray-800 dark:text-gray-200">Kinetiqo Agents</h4>
        </div>
        <div class="flex items-center gap-3">
            <label class="inline-flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300" for="strava-agents-enabled">
                <input id="strava-agents-enabled"
                       type="checkbox"
                       class="rounded border-gray-300 dark:border-zinc-600 text-amber-600 focus:ring-amber-500">
                Enable AI Agent
            </label>
        </div>
    </div>

    <!-- Description & Tag Pills -->
    <p class="text-xs text-gray-500 dark:text-gray-400">
        Inject dynamic AI analysis into your Strava descriptions by including the
        <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
            {{ai-agent}}
        </span>
        placeholder.
    </p>

    <!-- Sub-panel Inputs -->
    <div>
        <label for="strava-agent-prompt" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            Agent Prompt Instructions
        </label>
        <textarea id="strava-agent-prompt"
                  rows="3"
                  class="w-full px-3 py-2 text-xs font-sans rounded-lg border border-gray-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-gray-800 dark:text-gray-200 focus:ring-2 focus:ring-amber-500 focus:outline-none transition"></textarea>
    </div>
</div>
```

---

## 7. Tools Panels & Sidebars (Mega Stats & Fondo-o-meter Infographics)

Sidebar control boxes appear in the left panels of infographic and poster generators (e.g. "Mega Stats Size", "Period", "Appearance", "Stats Options").

### 7.1 Box Container (`.control-box`)
- **Outer Shell**:
  - Light mode: `background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 16px; overflow: hidden;`.
  - Dark mode: `background: #18181b; border-color: #27272a;`.

### 7.2 Collapsible Header (`.control-box-header`)
- **Header Layout**:
  - `padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none;`.
  - Light: `background: #f9fafb; border-bottom: 1px solid #e5e7eb;`.
  - Dark: `background: #202023; border-color: #27272a;`.
  - When collapsed: `border-bottom: none;`.
- **Title**: `font-size: 0.875rem; font-weight: 600; color: #374151; dark:color: #d1d5db;`.
- **Chevron Toggle**:
  - SVG icon (`width: 16px; height: 16px; transition: transform 0.2s ease;`).
  - When header has class `.collapsed`, icon rotates: `transform: rotate(-90deg);`.

### 7.3 Box Body (`.control-box-body`)
- **Padding**: `padding: 14px;`.
- **Collapse Toggle**: When collapsed, `.control-box-body.collapsed { display: none !important; }`.
- **State Persistence**: Collapse states must be saved to `localStorage` (e.g. `statsBoxCollapsed_statsPeriod`) and restored on page load.

### 7.4 Standardized Control Row Pattern (`.control-row`)
Each setting row inside the body uses `.control-row`:
- `display: flex; align-items: center; gap: 8px; margin-bottom: 10px;`.
- **Row Label**: `font-size: 0.75rem; font-weight: 500; min-width: 72px; color: #6b7280; dark:color: #9ca3af; flex-shrink: 0;`.

### 7.5 Specialized Sidebar Controls

#### A. Range Sliders (`_control_range.html`)
- Slider track: `flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer`.
- Trailing value indicator: `<span class="text-xs w-10 text-right text-gray-600 dark:text-gray-400">100%</span>`.

#### B. Color Pickers with "None" Reset (`_control_color_tint.html`)
- Color swatch: `h-8 w-12 p-0.5 rounded border border-gray-300 dark:border-gray-600 cursor-pointer`.
- "None" clear button: `h-8 px-2.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-zinc-800 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-50`.
- Trailing hex indicator: `<span class="text-xs text-gray-500 dark:text-gray-400 w-10 text-right">None</span>`.

#### C. Dropdown Selects (`_control_year_select.html`, `_font_select.html`)
- Select element: `h-8 px-2 rounded border border-gray-300 dark:border-gray-600 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white flex-1 focus:outline-none focus:ring-1 focus:ring-blue-500`.

#### D. Checkbox Grids (Visible Stats Standard)
- Checkbox label text: Uniform `text-xs` (12px) font size across light and dark modes.
- Input spacing: `flex-shrink-0 mr-1` and `style="margin-right: 3px;"`.
- Truncation container: Label text enclosed in `<span class="truncate">` to guarantee zero text wrapping or column overflow.

### 7.6 Compliant Tools Panel HTML Example
```html
<div class="control-box">
    <!-- Header with Chevron -->
    <div class="control-box-header" data-box-id="statsAppearance">
        <h4 class="text-gray-900 dark:text-gray-100">Appearance</h4>
        <button type="button"
                class="collapse-toggle-btn text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 p-0.5 focus:outline-none"
                aria-label="Toggle Appearance section">
            <svg class="chevron-icon w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
        </button>
    </div>

    <!-- Body Content -->
    <div class="control-box-body">
        <!-- Range Slider Row -->
        <div class="control-row">
            <label for="stats-opacity">Opacity</label>
            <input type="range"
                   id="stats-opacity"
                   min="0"
                   max="100"
                   value="80"
                   class="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
                   aria-label="Opacity">
            <span id="stats-opacity-val" class="text-xs w-10 text-right text-gray-600 dark:text-gray-400">80%</span>
        </div>

        <!-- Color Picker Row -->
        <div class="control-row">
            <label for="stats-tint">Tint Color</label>
            <div class="flex items-center gap-2 flex-1 justify-end">
                <input type="color"
                       id="stats-tint"
                       value="#000000"
                       class="h-8 w-12 p-0.5 rounded border border-gray-300 dark:border-gray-600 cursor-pointer"
                       aria-label="Tint Color">
                <button type="button"
                        id="stats-tint-clear"
                        class="h-8 px-2.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700 text-xs text-gray-600 dark:text-gray-300 transition">
                    None
                </button>
                <span id="stats-tint-val" class="text-xs text-gray-500 dark:text-gray-400 w-10 text-right">#000000</span>
            </div>
        </div>
    </div>
</div>
```

---

## 8. Summary Checklist for Code Reviews

When reviewing or generating GUI elements in Kinetiqo, ensure compliance with these core tenets:

1. **Fixed Button Heights**: All grid action buttons must enforce `h-[40px] px-3 py-2 text-sm flex items-center`.
2. **Accessible Labels**: Every `<input>`, `<select>`, and `<textarea>` must have an associated `<label for="id">` or explicit `aria-label` (Sonar Web:S6853).
3. **No Accompanying Text on Waiting Buttons**: Asynchronous actions must replace button text with `kinetiqo-loading-32x32.webp` and apply `opacity-60 cursor-wait` (ui-loading-standards).
4. **Static Number Methods**: Inline scripts must always use `Number.parseInt(str, 10)`, `Number.parseFloat(str)`, etc., never global `parseInt()` (Sonar javascript:S7773).
5. **Dual Theme Support**: Every component must specify both light mode and `dark:...` utility classes.
6. **No External Assets**: All styles, icons, fonts, and scripts must be 100% self-hosted; never introduce external CDN links.

