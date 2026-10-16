# Swift

## Scanner coverage
- Files: `*Tests.swift`, `*Test.swift` that import `XCTest` or `Testing`.
- Tests: XCTest `func test...` and Swift Testing `@Test` functions.
- Group flags: `@Suite(.disabled(...))`.
- Not seen: Quick/Nimble specs (`it("...") {}`), each `@Test(arguments:)` case (counted once).

## Quality checks
- `XCTestExpectation` created but never awaited with `wait(for:)` or `fulfillment(of:)`.
- Force unwraps where `XCTUnwrap`/`#require` should stop the test with a message.
- `#expect` where `#require` is needed to stop after a failed precondition.
- `XCTAssertThrowsError` without inspecting the error.
- State shared through class-level properties across test methods; main-actor isolation of UI code.

## False positives
- `no_assert`: Nimble `expect(x).to(...)` is not counted as an assertion.
- `nondeterministic`: `Date()` used only for timing.

## Run and coverage
- Single test: `swift test --filter FooTests/testBar`, or `xcodebuild test -scheme <Scheme> -destination '<dest>' -only-testing:<Target>/FooTests/testBar` for Xcode projects.
- Coverage: `swift test --enable-code-coverage` or `xcodebuild ... -enableCodeCoverage YES`.
