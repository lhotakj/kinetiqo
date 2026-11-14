---
name: python-standards
description: Enforce SonarQube rules and modern Python standards in Kinetiqo: cryptographic randomness with secrets (python:S2245), timezone-aware UTC datetimes, path traversal validation (pythonsecurity:S8707), and anonymous user safety.
---

# Python Standards & Clean Code in Kinetiqo

## 1. Cryptographic Randomness over Pseudorandom (SonarQube python:S2245)

Never use Python's pseudorandom `random` module (`random.choice`, `random.randint`, `random.random`, `random.sample`) in application code, CLI tools, or data generators. SonarQube flags all occurrences under rule `python:S2245`.

### Modern Equivalents
- **Random Choice**: `secrets.choice(seq)` instead of `random.choice(seq)`
- **Random Integer**: `secrets.randbelow(n)` instead of `random.randrange(n)` or `random.randint(0, n - 1)`
- **Random Token**: `secrets.token_hex(nbytes)` or `secrets.token_urlsafe(nbytes)`

> **Unit Testing Exception**: `random.Random(seed)` is permitted ONLY inside `tests/` files when reproducible test datasets require fixed seeds.

---

## 2. Modern Timezone-Aware UTC Datetimes

Python 3.11+ deprecated naive UTC methods `datetime.utcnow()` and `datetime.utcfromtimestamp()`, scheduling them for removal.

### Modern Equivalents
- **Current UTC Datetime**: `datetime.now(timezone.utc)` (never `datetime.utcnow()`)
- **From Timestamp**: `datetime.fromtimestamp(ts, tz=timezone.utc)` (never `datetime.utcfromtimestamp(ts)`)
- **Naive UTC for Legacy DB**: `datetime.now(timezone.utc).replace(tzinfo=None)`

---

## 3. Path Traversal & Boundary Validation (SonarQube pythonsecurity:S8707)

Any CLI script or web handler that receives file paths must canonically resolve and validate them against an approved boundary root before reading, writing, or deleting files.

```python
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

def resolve_safe_path(user_path: str | Path, base_dir: Path = _REPO_ROOT) -> Path:
    target = (base_dir / user_path).resolve()
    if not target.is_relative_to(base_dir):
        raise ValueError(f"Path traversal detected: {target} outside {base_dir}")
    if target.is_symlink():
        raise ValueError(f"Target cannot be a symlink: {target}")
    return target
```

---

## 4. Flask-Login Anonymous User Safety

Never assume `current_user` has `.id` or other authenticated attributes without checking `is_authenticated`:
```python
# ❌ Avoid:
user_id = current_user.id  # Fails with AttributeError if AnonymousUserMixin

# ✅ Use:
if current_user.is_authenticated:
    user_id = current_user.id
else:
    user_id = None  # Or return 401 / redirect
# Or:
user_id = getattr(current_user, "id", None)
```

---

## 5. Prohibition of Bare `assert` in Production Code (SonarQube python:S5905 / python:S5960)

Never use `assert` statements in non-test production code, CLI commands, utility modules, or database repositories.

### 5.1 Rationale
In Python, `assert` statements are purely diagnostic and are stripped out completely by the Python bytecode compiler when optimizations are enabled (`python -O` or `PYTHONOPTIMIZE=1`). Depending on `assert` for control flow, invariants, or parameter validation leads to critical security vulnerabilities and unintended fallthrough.

### 5.2 Compliant Replacements
- For argument validation: Raise `ValueError`, `TypeError`, or return explicit error payloads (HTTP 400/422).
- For internal sanity checks: Use explicit `if` conditionals with fallbacks or raise `RuntimeError`.

```python
# ❌ Non-compliant (production code assertion):
if placement == UPDATE_STRAVA_PLACEMENT_BEGIN:
    return rendered + desc
assert placement == UPDATE_STRAVA_PLACEMENT_END
return desc + rendered

# ✅ Compliant:
if placement == UPDATE_STRAVA_PLACEMENT_BEGIN:
    return rendered + desc
return desc + rendered
```

---

## 6. Test Class & Assertion Method Standards (SonarQube python:S5905 in tests)

All unit tests in Kinetiqo must be structured within `unittest.TestCase` test classes and use official assertion methods rather than bare `assert` statements.

### 6.1 Requirements
1. **TestCase Subclass**: Group related unit tests inside `class TestFeatureName(unittest.TestCase):`.
2. **Standard Assertion Methods**: Use `self.assertEqual(...)`, `self.assertGreater(...)`, `self.assertIn(...)`, `self.assertTrue(...)` instead of bare `assert`. Bare `assert` statements inside standalone functions or functions that catch `AssertionError` trigger SonarQube rule `python:S5905`.
3. **No Integration Fixtures by Default**: Follow Kinetiqo's mocked unit test philosophy (`AGENTS.md` Section 2) using `unittest.mock.patch`.

```python
# ❌ Non-compliant (bare assert in standalone function):
def test_calculate_zones():
    zones = calculate_coggan_zones([200], 250)
    assert len(zones) == 7

# ✅ Compliant (unittest.TestCase with assertion methods):
class TestCalculateZones(unittest.TestCase):
    def test_calculate_zones(self):
        zones = calculate_coggan_zones([200], 250)
        self.assertEqual(len(zones), 7)
```

