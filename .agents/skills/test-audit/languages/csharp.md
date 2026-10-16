# C#

## Scanner coverage
- Files: `*Test.cs`, `*Tests.cs`.
- Tests: xUnit `[Fact]`/`[Theory]`, NUnit `[Test]`/`[TestCase]`/`[TestCaseSource]`, MSTest `[TestMethod]`/`[DataTestMethod]`, `[SkippableFact]`, `[RetryFact]`; repeated `[TestCase]` rows form one test.
- Group flags: class-level `[Ignore]`/`[Explicit]`.
- Not seen: test files named otherwise (for example `*Specs.cs`), SpecFlow/Reqnroll feature files.

## Quality checks
- `async void` test methods lose exceptions; `.Result`/`.Wait()` can deadlock.
- `[InlineData]`/`[TestCase]` rows covering boundaries and invalid input.
- Moq loose mocks returning defaults that hide missing setups.
- FluentAssertions `x.Should()` without an assertion method checks nothing.
- State shared through `IClassFixture`/`[OneTimeSetUp]`.

## False positives
- `skip`: `[Explicit]` tests meant to run manually.
- `nondeterministic`: `DateTime.Now` used only for timing; a `TimeProvider` injected by a shared fixture.
- `snapshot_only`: Verify snapshots that are the reviewed contract.

## Run and coverage
- Single test: `dotnet test --filter "FullyQualifiedName~Namespace.FooTests.Bar"`.
- Coverage, only if coverlet.collector is referenced: `dotnet test --collect:"XPlat Code Coverage"`.
