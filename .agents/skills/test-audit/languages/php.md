# PHP

## Scanner coverage
- Files: `*Test.php`.
- Tests: PHPUnit `test*` methods, `#[Test]`, `@test` docblocks; Pest `it()`/`test()`.
- Not seen: Pest `describe()` group skips, Codeception `*Cest.php`, each `@dataProvider` row (counted once).

## Quality checks
- `assertEquals` (loose `==`) where `assertSame` is the contract.
- `expectException` placed after the throwing call is never checked.
- Data providers covering boundaries and invalid input.
- `markTestSkipped` in `setUp` silently skipping a whole class.
- Database tests without a transaction or refresh, leaking state between tests.

## False positives
- `mock_only_assert`: Mockery `shouldReceive` expectations verified at teardown are the real contract for side-effect collaborators.
- `no_assert`: `$this->expectNotToPerformAssertions()` tests.
- `nondeterministic`: `Carbon::setTestNow` in a base `TestCase` (another file).

## Run and coverage
- Single test: `vendor/bin/phpunit --filter 'FooTest::testBar'` or `vendor/bin/pest --filter "title"`.
- Coverage, only with Xdebug or PCOV installed: `vendor/bin/phpunit --coverage-text`.
