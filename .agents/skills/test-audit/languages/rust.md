# Rust

## Scanner coverage
- Files: any `.rs` containing a test attribute, so both `src/` unit tests (`mod tests`) and `tests/` integration tests.
- Tests: `#[test]`, `#[tokio::test]`, `#[async_std::test]`, `#[rstest]`, `#[test_case(...)]` followed by `fn`; attribute lines directly above belong to the test.
- Not seen: doctests in `///` comments, tests produced by custom macros without a visible attribute.

## Quality checks
- `#[should_panic]` without `expected = "..."` passes on any panic.
- `unwrap()`/`expect()` as the only check: it rejects `Err`/`None` but never checks the value.
- Tests returning `Result` that rely on `?` only.
- Tests sharing files, ports, or environment variables while cargo runs them in parallel threads.
- `#[ignore]` without a reason string.

## False positives
- `no_assert`: tests relying on `unwrap()`, `expect()`, or `?`; proptest `prop_assert!`/`prop_assert_eq!` are not counted as assertions.
- `swallowed_error`: `let _ = ...` for an intentional drop.
- `nondeterministic`: randomness inside property tests that report the seed on failure.

## Run and coverage
- Single test: `cargo test name -- --exact`; `cargo test -- --include-ignored` shows ignored tests.
- Coverage, only if installed: `cargo llvm-cov` or `cargo tarpaulin`.
