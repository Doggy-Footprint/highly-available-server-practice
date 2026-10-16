# C/C++

## Scanner coverage
- Files: `*_test.{cc,cpp,cxx}`, `*_unittest.{cc,cpp}`, `test_*.{cc,cpp}`, `*Test.cpp`, `*Tests.cpp` that use a test macro.
- Tests: GoogleTest `TEST`/`TEST_F`/`TEST_P`/`TYPED_TEST`/`TYPED_TEST_P` (named `Suite.Name`), Catch2/doctest `TEST_CASE`/`SCENARIO`/`TEST_CASE_METHOD`.
- Not seen: Catch2 `SECTION`s (counted inside their test case), `INSTANTIATE_TEST_SUITE_P` parameter sets, Boost.Test, plain C frameworks (Unity, CMocka).

## Quality checks
- `EXPECT_*` for a precondition that later code depends on; use `ASSERT_*` to stop.
- Floating-point results compared with `EXPECT_EQ` instead of `EXPECT_NEAR`/`EXPECT_DOUBLE_EQ`.
- `EXPECT_CALL` set after the call it should observe.
- `NiceMock` hiding unexpected calls that `StrictMock` would reject.
- Memory errors and undefined behavior hidden by a passing run; use sanitizer builds when the project has them.

## False positives
- `no_assert`: project-specific assertion macros.
- `sleep`: `sleep_for` in tests that deliberately exercise timing.
- `nondeterministic`: `std::random_device` used only to seed a generator whose seed is logged.

## Run and coverage
- Single test: `ctest --test-dir build -R 'Suite.Name'`, or the test binary with `--gtest_filter=Suite.Name` (`--gtest_repeat=N` for flakiness); Catch2 binaries take the test name as an argument.
- Coverage, only if the build already has a coverage configuration (`--coverage` flags, a coverage preset, `gcovr`/`llvm-cov` targets).
