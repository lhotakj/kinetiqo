# Kinetiqo Coding Skills & Quality Guidelines

This document outlines key coding practices, SonarQube rule compliance, and standards for the Kinetiqo codebase.

---

## 1. JavaScript Standards: Avoid Global Number Functions (SonarQube javascript:S7773)

### Rule Details
- **Rule Key**: [`javascript:S7773`](https://sonarcloud.io/organizations/lhotakj-github/rules?open=javascript%3AS7773&rule_key=javascript%3AS7773)
- **Title**: Number static methods and properties should be preferred over global equivalents
- **Scope**: All `.js` files and inline `<script>` blocks in Jinja templates (`.html`).

### Rationale
ES2015 introduced static methods and properties on `Number` for consistency and to avoid global scope pollution. Legacy global functions (`parseInt`, `parseFloat`, `isNaN`, `isFinite`) pollute the global scope and have legacy type-coercion quirks.

### Guidelines & Modern Equivalents

1. **Integer Parsing**:
   - ❌ **Avoid**: `parseInt(value, 10)`
   - ✅ **Use**: `Number.parseInt(value, 10)` (always provide an explicit radix).

2. **Float Parsing**:
   - ❌ **Avoid**: `parseFloat(value)`
   - ✅ **Use**: `Number.parseFloat(value)`

3. **NaN Checking**:
   - ❌ **Avoid**: `isNaN(value)`
   - ✅ **Use**: `Number.isNaN(value)` (or `Number.isNaN(Number(value))` if type coercion is required).

4. **Finite Checking**:
   - ❌ **Avoid**: `isFinite(value)`
   - ✅ **Use**: `Number.isFinite(value)` (or `Number.isFinite(Number(value))` if type coercion is required).

5. **NaN Constant**:
   - ❌ **Avoid**: `NaN`
   - ✅ **Use**: `Number.NaN`

---

## 2. Additional Web & SonarQube Guidelines

- **Sonar Web:S5725 (XSS Output Encoding)**: Jinja2 autoescaping is enabled by default. Use `|tojson` when serializing objects into `<script>` blocks. Never use `|safe` without strict sanitization.
- **Sonar Web:S6853 (Form Accessibility)**: Every form input, select, and textarea must have an associated `<label for="...">` or `aria-label`.
- **Line Endings Standard**: Use Unix/Linux line endings (**LF / `\n`**), never CRLF. UTF-8 without BOM.
