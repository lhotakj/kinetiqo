---
name: ui-loading-standards
description: Enforce uniform UI loading and waiting indicators across Kinetiqo using kinetiqo-loading-32x32.webp without accompanying text in action buttons.
---

# UI Loading & Waiting Standards in Kinetiqo

## 1. Unified Asset: `kinetiqo-loading-32x32.webp`

All loading indicators, waiting spinners, progress states, export buttons, and upload actions in Kinetiqo must exclusively use the native animated WebP asset:

- **Path**: `src/kinetiqo/web/static/img/kinetiqo-loading-32x32.webp`
- **Jinja2 Reference**: `{{ url_for('static', filename='img/kinetiqo-loading-32x32.webp') }}`
- **Client JS / Inline HTML Reference**: `/static/img/kinetiqo-loading-32x32.webp`
- **Important**: This is a 60-frame native animated WebP graphic. **Never apply CSS spin animations** (e.g. `animate-spin` or CSS `@keyframes spin`) as the image is already animated natively.

---

## 2. Action Button Waiting Standard (Exports, Uploads, Fetching)

Whenever a user clicks an action button that triggers an asynchronous operation (such as file export, data upload, map regeneration, or synchronization):

1. **No Text During Waiting**: Do NOT render text like `"Exporting..."`, `"Uploading..."`, or `"Syncing..."` on the button. Only render the rotating WebP icon (`kinetiqo-loading-32x32.webp`).
2. **Disabled State & Waiting Cursor**:
   - Set `btn.disabled = true;`
   - Add waiting classes: `btn.classList.add('opacity-60', 'cursor-wait');`
3. **Preserve Original State**:
   - Store the original button markup before modification: `const origHtml = btn.innerHTML;`
4. **Guaranteed Restoration (`finally` block)**:
   - Always restore the original button state in a `finally` block:
     ```javascript
     const btn = this;
     const origHtml = btn.innerHTML;
     btn.disabled = true;
     btn.classList.add('opacity-60', 'cursor-wait');
     btn.innerHTML = '<img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading..." class="h-4 w-4 inline-block mx-auto" width="16" height="16">';

     try {
         // Perform async operation (fetch, file export, etc.)
         await doAsyncOperation();
     } finally {
         btn.disabled = false;
         btn.classList.remove('opacity-60', 'cursor-wait');
         btn.innerHTML = origHtml;
     }
     ```

---

## 3. Image Upload Buttons (`<label>` + `<input type="file">`)

For image upload controls (such as `_image_upload_buttons.html`):

- The upload button is a styled `<label>` containing an `<img>` spinner and a `<span>` text element.
- **Initial Markup Rule**: Never put `inline-block` on the spinner `<img>` class list when combined with `hidden` (in Tailwind CSS v4, `.inline-block` overrides `.hidden` due to utility cascade order). Always specify `class="hidden h-5 w-5 flex-shrink-0" style="display: none;"`.
- When loading starts:
  - Add waiting classes to label: `uploadBtn.classList.add('opacity-60', 'pointer-events-none', 'cursor-wait');`
  - Show the spinner: `uploadSpinner.classList.remove('hidden'); uploadSpinner.style.display = 'inline-block';`
  - Hide the text completely: `uploadText.classList.add('hidden'); uploadText.style.display = 'none';`
  - Disable related inputs: `uploadInput.disabled = true;`
  - Set body cursor: `document.body.style.cursor = 'wait';`
- When loading ends:
  - Remove waiting classes from label.
  - Hide the spinner: `uploadSpinner.classList.add('hidden'); uploadSpinner.style.display = 'none';`
  - Restore the text: `uploadText.classList.remove('hidden'); uploadText.style.display = '';`
  - Re-enable related inputs.
  - Reset body cursor: `document.body.style.cursor = '';`

---

## 4. Chart & Container Overlays

For full-container data loading states (such as Map, Fitness & Freshness, FTP History, VO₂max):

- Display the rotating WebP centered above a clear status message:
  ```html
  <div id="chart-overlay" class="absolute inset-0 flex flex-col items-center justify-center bg-white dark:bg-gray-800 bg-opacity-75 dark:bg-opacity-75 z-10 gap-3">
      <img id="chart-overlay-spinner" src="{{ url_for('static', filename='img/kinetiqo-loading-32x32.webp') }}" alt="Loading..." class="h-8 w-8 inline-block" width="32" height="32">
      <p class="text-sm font-medium text-gray-600 dark:text-gray-400">Loading chart data...</p>
  </div>
  ```
- **Error State Handling**: If data fetching fails, hide the spinner (`spinner.style.display = 'none'`) and display only the error message text.

---

## 5. Sync Progress State

During activity sync (fast or full), before the text `"Sync in progress..."`, render the loading icon:
```html
<div class="text-center pt-4 border-t border-gray-200">
    <p class="text-sm font-medium mb-3 inline-flex items-center justify-center gap-2 sync-progress-text">
        <img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading..." class="h-4 w-4 inline-block" width="16" height="16">
        <span>Sync in progress...</span>
    </p>
</div>
```
- **Text Color Requirement**: The text color MUST be styled via `.sync-progress-text` in `common.css` (`color: #000000 !important;` in light mode and `body.dark .sync-progress-text, html.dark .sync-progress-text { color: #ffffff !important; }` in dark mode) ensuring crisp black in light mode and pure white in dark mode.
 
---

## 6. DataTables Loading & Processing State

For DataTables 2.x grids (such as the activities grid in `activities.html`):

1. **Hide Default 4-Dot Animation**: DataTables 2.x automatically appends a container with 4 animated bouncing dots (`div.dt-processing > div:last-child`). This must be suppressed in `common.css`:
   ```css
   /* Hide DataTables 2.x default bouncing dots animation */
   div.dt-processing > div:last-child,
   div.dt-processing > div:not(:first-child) {
       display: none !important;
   }
   ```
2. **Centered Processing Card**: Style `div.dt-processing` as a centered floating translucent card matching light/dark mode theme:
   ```css
   div.dt-processing {
       position: absolute;
       top: 50%;
       left: 50%;
       transform: translate(-50%, -50%);
       margin: 0 !important;
       padding: 0.75rem 1.25rem !important;
       width: auto !important;
       min-width: 80px;
       border-radius: 0.5rem;
       background-color: rgba(255, 255, 255, 0.95);
       border: 1px solid #e5e7eb;
       box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
       z-index: 50;
   }

   body.dark div.dt-processing,
   html.dark div.dt-processing {
       background-color: rgba(38, 38, 38, 0.95);
       border-color: #404040;
       box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4);
   }
   ```
3. **DataTables Language Configuration**: In the DataTable initialization options, configure `processing` and suppress raw `loadingRecords` text:
   ```javascript
   "processing": true,
   "language": {
       "processing": '<div class="flex justify-center items-center"><img src="{{ url_for(\'static\', filename=\'img/kinetiqo-loading-32x32.webp\') }}" alt="Loading..." class="h-8 w-8 inline-block" width="32" height="32"></div>',
       "loadingRecords": '&nbsp;'
   },
   ```


