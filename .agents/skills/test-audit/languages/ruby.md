# Ruby

## Scanner coverage
- Files: `*_spec.rb`, `test_*.rb`, `*_test.rb`.
- Tests: RSpec `it`/`specify`/`example`/`scenario` (with `x`/`f` prefixes) with a string title, minitest `def test_*`, Rails `test "..."`. Bodies end by indentation.
- Group flags: `xdescribe`/`xcontext`/`fdescribe`/`fcontext` and `skip:`/`focus:` metadata on `describe`/`context`.
- Not seen: anonymous one-liners `it { is_expected.to ... }` (not reported; review them by reading), `its(:attr)`, `shared_examples`/`it_behaves_like` (tests defined elsewhere), `skip` called inside a `before` hook.

## Quality checks
- `let!` or `before(:all)` state leaking between examples.
- `allow(...).to receive` stubs where an `expect(...).to receive` is the contract.
- `raise_error` without a class or message.
- FactoryBot `create` where `build` would do, slowing the suite and hiding unneeded records.
- `travel_to` without a block or matching `travel_back`.

## False positives
- `duplicate_name`: the same title in different `describe`/`context` blocks.
- `nondeterministic`: `travel_to`/`Timecop` in an `around` hook of `spec_helper.rb`.

## Run and coverage
- Single test: `bundle exec rspec path/foo_spec.rb:42`, `bin/rails test path/foo_test.rb:42`, or `ruby -Itest path/foo_test.rb -n test_bar`.
- Coverage, only if SimpleCov is required in `spec_helper.rb`/`test_helper.rb`: it writes `coverage/` on every run.
