# Python

## Scanner coverage
- Parsed with `ast`: every function or method whose name starts with `test`, at module level or in any class.
- Group flags: class decorators (`@unittest.skip`, `@pytest.mark.skip`/`xfail`, nested classes included) and module-level `pytestmark`.
- Not seen: tests collected through custom `python_functions`/`python_classes` settings, dynamically generated tests, `subTest` and `parametrize` cases (each counts as one test).
- Listed but possibly never run: pytest does not collect `test*` methods of classes not named `Test*` unless they subclass `unittest.TestCase`; check before judging such a test.

## Quality checks
- `parametrize` ids cover boundaries and error paths, not only typical values.
- `mock.patch` targets the name where it is looked up, not where it is defined; a wrong target lets the test pass against the real code.
- Statements after the raising call inside `with pytest.raises(...)` never run.
- `session`/`module`-scoped or `autouse` fixtures that share mutable state across tests.
- `pytest.approx` tolerances wide enough to hide a wrong result.

## False positives
- `no_assert`: Hypothesis tests that assert through helpers.
- `sleep`: `asyncio.sleep(0)` used to yield control.
- `nondeterministic`: a seed or `freeze_time` set in `conftest.py` (another file); `time.time()` used only to measure duration.
- `skip`: `skipif` on a platform condition that is false in CI.

## Run and coverage
- Single test: `pytest path/test_x.py::TestA::test_b` or `python3 -m unittest path.module.TestA.test_b`.
- Coverage, only if configured: `pytest --cov` (pytest-cov installed) or `coverage run -m pytest` (`.coveragerc` or `[tool.coverage]`).
