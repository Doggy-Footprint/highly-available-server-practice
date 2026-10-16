# JavaScript / TypeScript

## Scanner coverage
- Files: `*.test.*`, `*.spec.*` (js, jsx, ts, tsx, mjs, cjs) and any of those extensions under `__tests__/`.
- Tests: `it`/`test` with a string title, including `.skip`, `.only`, `.todo`, `.concurrent`, `.failing`, and `xit`, `xtest`, `fit`.
- Group flags: `describe.skip`/`xdescribe`/`context.skip`/`xcontext` and `describe.only`/`fdescribe`/`context.only`.
- Not seen: `test.each`/`it.each` tables (not reported; review them by reading), tests registered in loops or helpers, Cucumber steps.

## Quality checks
- Async tests that neither `await` nor return the promise; assertions after the test ends are lost.
- `done` callbacks called before the assertion, or never on the error path; `expect.assertions(n)` on async error paths.
- Fake timers installed but never advanced, so the code under test never runs.
- `jest.mock`/`vi.mock` hoisted module-wide, silently replacing modules other tests rely on.
- Snapshot updates committed without review (large `.snap` diffs).
- `toHaveBeenCalled()` where `toHaveBeenCalledWith(...)` is the contract; `toBeTruthy()` on objects.

## False positives
- `no_assert`: Testing Library `getBy*` queries and Playwright locator actions fail by throwing; custom `expectX` helpers.
- `duplicate_name`: the same title in different `describe` blocks.
- `sleep`: `setTimeout` under fake timers.
- `nondeterministic`: fake timers or `MockDate` installed in a setup file (`setupFiles`, `setupFilesAfterEach`).

## Run and coverage
- Single test: `npx jest path -t "title"`, `npx vitest run path -t "title"`, `npx mocha path --grep "title"`.
- Coverage, only if configured: `npx jest --coverage`, `npx vitest run --coverage` (a `@vitest/coverage-*` package installed), `c8`/`nyc` when in devDependencies.
