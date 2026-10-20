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

## 2. JavaScript Object Property Uniqueness (SonarQube javascript:S1534)

### Rule Details
- **Rule Key**: [`javascript:S1534`](https://sonarcloud.io/organizations/lhotakj-github/rules?open=javascript%3AS1534&rule_key=javascript%3AS1534)
- **Title**: Object literal syntax should not contain duplicate property names
- **Scope**: All `.js` files and inline `<script>` blocks in Jinja templates (`.html`).

### Rationale
Duplicate keys in object literals are confusing and cause one property definition to silently overwrite another. For instance, declaring `language: { processing: ... }` and later `language: { search: ... }` inside a DataTables configuration overwrites the loading spinner configuration entirely.

### Guidelines & Best Practice
Merge all configuration properties into a single unified object key:
```javascript
// ❌ Avoid (duplicate 'language' key triggers javascript:S1534 and overwrites processing)
const dtOptions = {
    language: { processing: '<img src="/static/img/loading.webp">' },
    // ...
    language: { search: 'Filter:' }
};

// ✅ Use (single unified object)
const dtOptions = {
    language: {
        processing: '<img src="/static/img/loading.webp">',
        search: 'Filter:'
    }
};
```

---

## 3. Python Security: Cryptographic Randomness over Pseudorandom (SonarQube python:S2245)

### Rule Details
- **Rule Key**: [`python:S2245`](https://sonarcloud.io/organizations/lhotakj-github/rules?open=python%3AS2245&rule_key=python%3AS2245)
- **Title**: Pseudorandom number generators should not be used in security-sensitive contexts
- **Scope**: All Python code (`src/` and `development/`).

### Rationale
Python's standard `random` module uses the Mersenne Twister algorithm, which is completely predictable. SonarQube flags all occurrences of `random` in production code. To eliminate security vulnerabilities and avoid false positives, Kinetiqo strictly standardizes on the standard library `secrets` module.

### Conversion Table

| Pseudorandom Method (`random`) | Cryptographically Secure Equivalent (`secrets`) | Notes |
|---|---|---|
| `random.choice(seq)` | `secrets.choice(seq)` | Uniform choice from non-empty sequence |
| `random.randrange(n)` / `randint(0, n-1)` | `secrets.randbelow(n)` | Bounded integer in range `[0, n)` |
| `random.sample(seq, k)` | `[secrets.choice(seq) for _ in range(k)]` | Or shuffle with cryptographic indices |
| Random hex / string | `secrets.token_hex(nbytes)` | Generates random hex string |

> **Testing Exception**: In unit tests (`tests/`), `random.Random(seed)` is allowed locally ONLY when a deterministic fixed seed is required for mock dataset repeatability.

---

## 4. Python Datetime: Modern Timezone-Aware UTC Datetimes

### Rationale
Python 3.11+ officially deprecated `datetime.datetime.utcnow()` and `datetime.datetime.utcfromtimestamp()`, scheduling them for complete removal in future Python versions. Calling them emits runtime `DeprecationWarning`s.

### Guidelines & Modern Equivalents

1. **Current UTC Datetime**:
   - ❌ **Avoid**: `datetime.utcnow()`
   - ✅ **Use**: `datetime.now(timezone.utc)` (or `datetime.now(timezone.utc).replace(tzinfo=None)` if naive UTC is strictly needed for legacy DB columns).

2. **From Timestamp**:
   - ❌ **Avoid**: `datetime.utcfromtimestamp(ts)`
   - ✅ **Use**: `datetime.fromtimestamp(ts, tz=timezone.utc)`

3. **Monkey-Patching Third-Party Deprecations**:
   - When external packages (e.g. Flask-Login 0.6.3) internally call `datetime.utcnow()`, apply compatibility shims during Flask application bootstrap (`src/kinetiqo/web/app.py`) to keep CI/CD logs free of deprecation noise.

---

## 5. Python Security: Path Traversal & Boundary Validation (SonarQube pythonsecurity:S8707)

### Rule Details
- **Rule Key**: [`pythonsecurity:S8707`](https://sonarcloud.io/organizations/lhotakj-github/rules?open=pythonsecurity%3AS8707&rule_key=pythonsecurity%3AS8707)
- **Title**: Path Traversal via untrusted path parameters
- **Scope**: CLI scripts, web upload handlers, and development utilities.

### Rationale
Accepting file paths from CLI arguments, query parameters, or config files without canonical resolution and boundary checks can permit arbitrary file overwrite or unauthorized access via `../` path traversal.

### Implementation Pattern
```python
from pathlib import Path

# 1. Establish an absolute root boundary
_REPO_ROOT = Path(__file__).resolve().parent.parent

def safe_resolve_path(user_input: str | Path, base_dir: Path = _REPO_ROOT) -> Path:
    # 2. Resolve target path canonically
    target = (base_dir / user_input).resolve()
    
    # 3. Enforce containment within boundary
    if not target.is_relative_to(base_dir):
        raise ValueError(f"Path traversal detected: {target} is outside {base_dir}")
        
    # 4. Reject symlink write targets
    if target.is_symlink():
        raise ValueError(f"Target cannot be a symlink: {target}")
        
    return target
```

---

## 6. Additional Web & SonarQube Guidelines

- **Sonar Web:S5725 (XSS Output Encoding)**: Jinja2 autoescaping is enabled by default. Use `|tojson` when serializing objects into `<script>` blocks. Never use `|safe` without strict sanitization.
- **Sonar Web:S6853 (Form Accessibility)**: Every form input, select, and textarea must have an associated `<label for="...">` or `aria-label`.
- **Anonymous User Safety**: Never access `current_user.id` or user attributes directly without checking `if current_user.is_authenticated:`. Use `getattr(current_user, 'id', None)` for safe fallbacks.
- **Line Endings Standard**: Use Unix/Linux line endings (**LF / `\n`**), never CRLF. UTF-8 without BOM.
