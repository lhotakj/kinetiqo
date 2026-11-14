---
name: javascript-standards
description: Enforce SonarQube rules and modern ECMAScript standards for JavaScript code in Kinetiqo, specifically avoiding legacy global number methods (javascript:S7773).
---

# JavaScript Standards & Clean Code in Kinetiqo

## 1. Number Static Methods & Properties (SonarQube javascript:S7773)

ES2015 (ES6) introduced static methods and properties on `Number` for consistency, modularity, and to prevent global scope pollution.
In Kinetiqo, all JavaScript code—both in standalone `.js` files and inline `<script>` blocks within Jinja2 `.html` templates—must strictly prefer static `Number` methods over their global equivalents.

### 1.1 Conversion Table

| Legacy Global Construct | Recommended Modern Standard | Notes |
|---|---|---|
| `parseInt(str, radix)` | `Number.parseInt(str, radix)` | Always supply an explicit radix (e.g., `10` or `16`). |
| `parseFloat(str)` | `Number.parseFloat(str)` | Parses floating-point number. |
| `isNaN(val)` | `Number.isNaN(val)` | Note: `Number.isNaN` does not coerce strings or other types to `NaN`. If type coercion is required, write `Number.isNaN(Number(val))`. |
| `isFinite(val)` | `Number.isFinite(val)` | Note: `Number.isFinite` does not coerce. Use `Number.isFinite(Number(val))` when type conversion is needed. |
| `NaN` | `Number.NaN` | Prefer the namespaced constant over the global variable. |

### 1.2 Examples

#### Integer Parsing
```javascript
// Non-compliant (triggers SonarQube javascript:S7773):
const width = parseInt(input.value, 10);

// Compliant:
const width = Number.parseInt(input.value, 10);
```

#### Float Parsing
```javascript
// Non-compliant (triggers SonarQube javascript:S7773):
const pct = parseFloat(box.style.left) / 100;

// Compliant:
const pct = Number.parseFloat(box.style.left) / 100;
```

#### NaN & Finite Checks
```javascript
// Non-compliant:
if (isNaN(seconds) || seconds < 0) { ... }
if (isFinite(value)) { ... }

// Compliant:
const sec = Number(seconds);
if (Number.isNaN(sec) || sec < 0) { ... }
if (Number.isFinite(value)) { ... }
```

---

## 2. Object Literal Property Uniqueness (SonarQube javascript:S1534)

In JavaScript objects (and inline configs in templates), duplicate property keys trigger SonarQube `javascript:S1534` and result in silent overwrites.

### Example: DataTables Configuration
```javascript
// ❌ Non-compliant (duplicate 'language' property overwrites 'processing' loading indicator)
const options = {
    language: { processing: '<img src="/static/img/loading.webp">' },
    pageLength: 25,
    language: { search: 'Search:' }
};

// ✅ Compliant (single unified object)
const options = {
    language: {
        processing: '<img src="/static/img/loading.webp">',
        search: 'Search:'
    },
    pageLength: 25
};
```

---

## 3. Promise Handling & Floating Promises (SonarQube javascript:S6544)

In modern asynchronous JavaScript, promises must never be left "floating" (unhandled). Unhandled promises can silently swallow rejection errors, cause subtle race conditions, and fail SonarQube rule `javascript:S6544`.

### 3.1 Requirements
Every promise returned by an async function or API call must satisfy at least one of:
1. Be `await`ed inside an `async` function with appropriate `try/catch` error handling.
2. Chain a `.catch(...)` or `.then(..., onRejected)` rejection handler.
3. Be explicitly marked as intentionally unawaited using the `void` operator (e.g. `void loadSessions().catch(...)`).

### 3.2 Compliant Patterns
```javascript
// ❌ Non-compliant (floating promise in event listener / top-level):
document.getElementById('refresh').addEventListener('click', () => {
    loadSessions();
});
Promise.all([loadModels(), loadSessions()]);

// ✅ Compliant (void with rejection handler or explicit chain):
document.getElementById('refresh').addEventListener('click', () => {
    void loadSessions().catch((err) => console.error('Failed to reload sessions:', err));
});

void Promise.all([loadModels(), loadSessions()])
    .then(() => (sessionId ? openSession(sessionId) : null))
    .catch((error) => setStatus(error.message, true));
```

---

## 4. Catastrophic Backtracking Prevention in Regular Expressions (SonarQube javascript:S5852)

Regular expressions with nested quantifiers (such as `(A+)+`, `(A*)+`, or `(?:<tag>.*?<\/tag>)+`) exhibit polynomial or exponential worst-case time complexity when presented with non-matching or malformed inputs. SonarQube flags these under `javascript:S5852`.

### 4.1 Guidelines for Safe Regexes
1. **Never Nest Quantifiers**: Never place a lazy or greedy quantifier inside a repeated group (e.g. avoid `(?:.*?)+` or `(?:[^\n]*)+`).
2. **Use Strict Character Classes**: Instead of wildcards like `.*?`, constrain matches with negative character sets:
   - Inline markdown bold/italic: Use `/\*\*([^*\n\r]+)\*\*/g` instead of `/\*\*(.*?)\*\*/g`.
   - Single-line tags: Use `/<li class="...">(?:[^\n<]*)<\/li>/g` instead of `/<li class="...">.*?<\/li>/gis`.
   - Fenced code blocks: Use `/```([a-zA-Z0-9_-]*)\r?\n((?:[^`]|`(?!``))*?)```/g` to ensure closing backticks do not backtrack across lines.
   - Comment stripping: Use `/\/\/[^\r\n]*/g` instead of `/\/\/.*$/gm`.
3. **Bound Multiline Searches**: When stripping multiline blocks (e.g., Mermaid live editor notes), check string containment first (`if (str.includes(...))`) and bound line counts (`{0,4}`) rather than using unbounded `[\s\S]*?`.

