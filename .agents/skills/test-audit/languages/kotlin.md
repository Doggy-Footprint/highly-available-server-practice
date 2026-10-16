# Kotlin

## Scanner coverage
- Files: `*Test.kt`, `*Tests.kt`.
- Tests: JUnit annotations (`@Test`, `@ParameterizedTest`, `@RepeatedTest`, `@TestFactory`, `@RetryingTest`) on `fun`; backtick names are reported without backticks.
- Group flags: class-level `@Disabled`/`@Ignore`.
- Not seen: Kotest specs (`StringSpec`, `FunSpec` `test("...") {}`), Spek.

## Quality checks
- Coroutine code tested with `runBlocking` and real `delay` instead of `runTest`.
- MockK `relaxed = true` mocks returning defaults that hide missing stubs; `every { }` without a matching `verify`.
- `assertFailsWith<Exception>` / `shouldThrowAny` where a specific type is the contract.
- Shared state under JUnit 5 `@TestInstance(PER_CLASS)`.

## False positives
- `sleep`: `delay()` inside `runTest` uses virtual time.
- `no_assert`: custom infix assertions not named `should*`/`assert*`.
- `nondeterministic`: `Random(seed)` instances (only the unseeded `Random.next*` is flagged).

## Run and coverage
- Single test: `./gradlew test --tests 'FooTest.bar'`.
- Coverage, only if configured: Kover (`./gradlew koverHtmlReport`) or JaCoCo (`./gradlew jacocoTestReport`).
