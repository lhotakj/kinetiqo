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
