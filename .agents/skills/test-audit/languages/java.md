# Java

## Scanner coverage
- Files: `*Test.java`, `*Tests.java`.
- Tests: `@Test`, `@ParameterizedTest`, `@RepeatedTest`, `@TestFactory`, `@TestTemplate`, jqwik `@Property`, junit-pioneer `@RetryingTest`/`@RepeatedIfExceptionsTest`.
- Group flags: class-level `@Disabled`/`@Ignore`, including `@Nested` classes.
- Not seen: `*IT.java` integration tests, Spock/Groovy specs, TestNG `@Test(enabled = false)` (not flagged `skip`).

## Quality checks
- AssertJ `assertThat(x)` without a terminal assertion checks nothing, yet counts as an assertion.
- `@Test(expected = X.class)` passes if any line throws `X`; prefer `assertThrows` around the exact call.
- Mockito `when(...)` stubs never exercised (strict stubs report these) and `any()` matchers that hide wrong arguments.
- Static or `@BeforeAll` state shared between tests.
- Parameterized sources covering boundaries; `Thread.sleep` where Awaitility polling is intended.

## False positives
- `no_assert`: AssertJ BDD `then(x).isEqualTo(...)` and Hamcrest-only helpers not named `assert*`.
- `skip`: `Assumptions.assume*` skips only under specific conditions.

## Run and coverage
- Single test: `mvn -Dtest=FooTest#bar test` or `./gradlew test --tests 'FooTest.bar'`; `mvn verify` runs failsafe `*IT` tests.
- Coverage, only if the JaCoCo plugin is configured: `mvn jacoco:report` or `./gradlew jacocoTestReport`.
