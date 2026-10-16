# Go

## Scanner coverage
- Files: `*_test.go`. Tests: `func TestX(t *testing.T)` and `func FuzzX(f *testing.F)`.
- Not seen: `t.Run` subtests (their content counts toward the parent), testify `suite.Suite` methods (`func (s *S) TestX()`, the file is listed with no tests), `ExampleX` functions with `// Output:` (these are tests), benchmarks.

## Quality checks
- Table-driven cases cover boundaries and error returns, not only the happy path.
- `t.Fatal`/`t.FailNow` called from a goroutine other than the test's.
- `t.Errorf` followed by code that dereferences the failed value (should be `t.Fatalf`).
- Errors compared by message string instead of `errors.Is`/`errors.As`.
- `t.Parallel()` with captured loop variables (before Go 1.22) or shared package state.
- Golden files regenerated with an `-update` flag and committed without review.

## False positives
- `no_assert`: helpers that take `t` and call `t.Helper()`; testify suite assertions (`s.Equal`).
- `swallowed_error`: `_ = f.Close()` in cleanup.
- `broad_exception`: `assert.Error` where only the presence of an error is the contract.
- `nondeterministic`: `time.Now()` used to build a deadline or timeout.
- `skip`: `testing.Short()` skips that CI runs without `-short`.

## Run and coverage
- Single test: `go test ./pkg -run '^TestX$' -count=1` (`-count=1` bypasses the test cache); add `-race` when judging flakiness.
- Coverage: `go test ./... -cover` or `-coverprofile=cover.out` (built in).
