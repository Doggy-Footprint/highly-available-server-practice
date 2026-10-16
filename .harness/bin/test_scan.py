#!/usr/bin/env python3
import argparse
import ast
import bisect
import fnmatch
import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HEAVY_MOCK_THRESHOLD = 5
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".harness", ".agents", ".claude", ".codex",
}
INVENTORY_DIRS = {"test", "tests", "spec", "__tests__"}
JS_EXTENSIONS = ("js", "jsx", "ts", "tsx", "mjs", "cjs")
BODY_TEST_LOOKAHEAD = 10

# The single table of per-language patterns. Add a language or tune a signal here only.
# "tests" lists (start, name_after) alternatives: "start" matches the line that begins a test;
# its "name" group (optionally prefixed by a "prefix" group, joined with ".") is the test name or,
# when "name_after" is set, a regex searched on the lines following the start match.
# "model" is "brace" (body ends at the closing brace), "indent" (ruby), or None (python, via ast).
# "brace" is an opener regex whose last character is the opening brace; None means the first "{".
# "prefix" matches lines above a start that belong to the test (attributes, docblocks).
# "empty_open" matches an indent-model start line that opens an empty-checkable block.
# "group_skip"/"group_focused" match test-group markers whose block propagates the flag.
# "assert", "mock_assert" and "snapshot" are classified in that precedence: snapshot, mock, plain.
# "deterministic_guard" suppresses "nondeterministic" for the whole file.
LANGUAGES = {
    "python": {
        "globs": ["test_*.py", "*_test.py"],
        "dir_globs": {},
        "require": None,
        "tests": None,
        "model": None,
        "brace": None,
        "prefix": None,
        "empty_open": None,
        "group_skip": None,
        "group_focused": None,
        "skip": r"pytest\.mark\.skip(?:if)?\b|unittest\.skip(?:If|Unless)?\b|\bpytest\.skip\s*\(|\bself\.skipTest\s*\(|\bpytest\.importorskip\s*\(",
        "xfail": r"pytest\.mark\.xfail\b|\bpytest\.xfail\s*\(|\bexpectedFailure\b",
        "focused": None,
        "assert": r"\bassert\w*|\bpytest\.(?:raises|warns|fail)\b|\bself\.fail\s*\(",
        "sleep": r"\b(?:time|asyncio)\.sleep\s*\(",
        "mock": r"\b(?:Magic|Async)?Mock\s*\(|\b(?:mock\.)?patch(?:\.object|\.dict|\.multiple)?\s*\(|\bmocker\.\w+|\bmonkeypatch\.\w+|\bcreate_autospec\s*\(",
        "incomplete": r"\braise\s+NotImplementedError\b",
        "mock_assert": r"\.assert_(?:(?:not_)?called|(?:not_)?awaited|has_calls|any_call|has_awaits|any_await)\w*",
        "snapshot": r"\bassert\b[^\n]*==\s*snapshot\b|\bsnapshot\.assert_match\s*\(",
        "trivial_assert": r"\bassert\s+True\b(?!\s*(?:[=!<>.]|and\b|or\b|in\b|is\b))|\bassert\s*\((?:[^()\n,]|\([^()\n]*\))*,(?:[^()\n]|\([^()\n]*\))*\)[ \t]*(?:#.*)?$|\bself\.assert(?:True\(\s*True|False\(\s*False)\s*\)",
        "broad_exception": r"\b(?:pytest\.raises|self\.assertRaises)\(\s*(?:Base)?Exception\s*\)",
        "swallowed_error": r"\bexcept\b[^\n:]*:[ \t]*(?:\n[ \t]*)?(?:pass|\.\.\.)[ \t]*(?:#.*)?$",
        "nondeterministic": r"\brandom\.(?:random|randint|randrange|choice|choices|shuffle|sample|uniform|gauss)\s*\(|\bdatetime\.(?:now|utcnow|today)\s*\(|\bdate\.today\s*\(|\btime\.(?:time|time_ns)\s*\(|\buuid\.uuid[14]\s*\(",
        "deterministic_guard": r"\bfreeze_time\b|\bfreezegun\b|\brandom\.seed\s*\(|\btime_machine\b",
        "retry": r"@(?:pytest\.mark\.)?flaky\b",
    },
    "javascript": {
        "globs": [f"*.{kind}.{ext}" for kind in ("test", "spec") for ext in JS_EXTENSIONS],
        "dir_globs": {"__tests__": [f"*.{ext}" for ext in JS_EXTENSIONS]},
        "require": None,
        "tests": [
            (r"(?<![\w.$])(?:it|test|xit|xtest|fit)(?:\.(?:skip|only|concurrent|failing|fails|todo))*\s*\(\s*(?P<q>['\"`])(?P<name>.*?)(?P=q)", None),
        ],
        "model": "brace",
        "brace": r"(?:=>|\))\s*\{",
        "prefix": None,
        "empty_open": None,
        "group_skip": r"(?<![\w.$])(?:xdescribe|xcontext)\s*\(|(?<![\w.$])(?:describe|context)\.skip\s*\(",
        "group_focused": r"(?<![\w.$])fdescribe\s*\(|(?<![\w.$])(?:describe|context)\.only\s*\(",
        "skip": r"\.skip\b|(?<![\w.$])x(?:it|test)\s*\(",
        "xfail": r"\.(?:failing|fails)\b",
        "focused": r"\.only\b|(?<![\w.$])fit\s*\(",
        "assert": r"\bexpect(?:Type)?(?:Of)?\s*[(.]|\bassert\w*|\.should\b|\bt\.(?:is|true|false|deepEqual|equal|throws)\b",
        "sleep": r"\bsetTimeout\s*\(|\bsleep\s*\(",
        "mock": r"\b(?:jest|vi)\.(?:fn|mock|doMock|spyOn)\s*\(|\bsinon\.(?:stub|spy|mock|fake)\w*\s*\(",
        "incomplete": r"(?<![\w.$])(?:it|test)\.todo\b",
        "mock_assert": r"\bexpect\s*\([^\n;]*?\)\s*\.\s*(?:not\s*\.\s*)?(?:toHaveBeen\w*|toBeCalled\w*|toHaveReturned\w*|toHaveLastReturnedWith|toHaveNthReturnedWith)\s*\(|\bsinon\.assert\.\w+\s*\(",
        "snapshot": r"\bexpect\s*\([^\n;]*?\)\s*\.\s*(?:not\s*\.\s*)?(?:toMatch(?:Inline|File|Image)?Snapshot|toThrowErrorMatching(?:Inline)?Snapshot)\s*\(",
        "trivial_assert": r"\bexpect\(\s*(?:true|false)\s*\)\.(?:toBe|toEqual|toStrictEqual)\(\s*(?:true|false)\s*\)|\bexpect\(\s*(?:true|false)\s*\)\.to(?:BeTruthy|BeFalsy)\(\s*\)|\bassert(?:\.ok)?\(\s*true\s*\)",
        "broad_exception": r"\.toThrow(?:Error)?\(\s*\)",
        "swallowed_error": r"\bcatch\s*(?:\([^()]*\))?\s*\{\s*\}|\.catch\(\s*(?:\([^()]*\)|\w+)?\s*=>\s*\{\s*\}\s*\)",
        "nondeterministic": r"\bMath\.random\s*\(|\bDate\.now\s*\(|\bnew\s+Date\s*\(\s*\)|\bcrypto\.randomUUID\s*\(",
        "deterministic_guard": r"\b(?:jest|vi)\.useFakeTimers\s*\(|\b(?:jest|vi)\.setSystemTime\s*\(|\bMockDate\.set\s*\(|\bfaker\.seed\s*\(",
        "retry": r"\bjest\.retryTimes\s*\(|\bthis\.retries\s*\(|\{\s*retry\s*:",
    },
    "go": {
        "globs": ["*_test.go"],
        "dir_globs": {},
        "require": None,
        "tests": [
            (r"^func\s+(?P<name>Test\w*)\s*\(\s*\w+\s+\*testing\.T\s*\)", None),
            (r"^func\s+(?P<name>Fuzz\w*)\s*\(\s*\w+\s+\*testing\.F\s*\)", None),
        ],
        "model": "brace",
        "brace": None,
        "prefix": None,
        "empty_open": None,
        "group_skip": None,
        "group_focused": None,
        "skip": r"\b[tf]\.Skip(?:f|Now)?\s*\(|\btesting\.Short\s*\(\s*\)",
        "xfail": None,
        "focused": None,
        "assert": r"\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\s*\(|\b(?:assert|require)\.\w+",
        "sleep": r"\btime\.Sleep\s*\(",
        "mock": r"\bgomock\.\w+|\bNewMock\w*\s*\(|\.EXPECT\s*\(|\.On\s*\(",
        "incomplete": None,
        "mock_assert": r"\.(?:AssertExpectations|AssertCalled|AssertNumberOfCalls|AssertNotCalled)\s*\(|\.EXPECT\s*\(\s*\)",
        "snapshot": r"\bsnaps\.Match\w+\s*\(|\bcupaloy\.Snapshot\w*\s*\(",
        "trivial_assert": r"\b(?:assert|require)\.(?:True\(\s*\w+\s*,\s*true\s*\)|False\(\s*\w+\s*,\s*false\s*\))",
        "broad_exception": r"\b(?:assert|require)\.Error\(\s*\w+\s*,\s*[\w.]+\s*(?:,[^()\n]*)?\)",
        "swallowed_error": r"^[ \t]*_[ \t]*=[ \t]*[^=\s]|^[ \t]*\w+[ \t]*,[ \t]*_[ \t]*:?=[ \t]*[^=\s]",
        "nondeterministic": r"\btime\.Now\s*\(|\brand\.(?:Int|Intn|Int31|Int31n|Int63|Int63n|Uint32|Uint64|Float32|Float64|ExpFloat64|NormFloat64|Perm|Shuffle|N)\s*\(|\buuid\.(?:New|NewString|NewRandom)\s*\(",
        "deterministic_guard": r"\brand\.New\s*\(\s*rand\.NewSource\b|\brand\.Seed\s*\(|\bclockwork\.NewFakeClock\w*\s*\(",
        "retry": None,
    },
    "rust": {
        "globs": ["*.rs"],
        "dir_globs": {},
        "require": r"#\[(?:test|tokio::test|async_std::test|rstest|test_case)\b",
        "tests": [
            (r"^[ \t]*#\[(?:test|tokio::test|async_std::test|rstest|test_case)\b", r"\bfn\s+(?P<name>\w+)"),
        ],
        "model": "brace",
        "brace": None,
        "prefix": r"^[ \t]*#\[",
        "empty_open": None,
        "group_skip": None,
        "group_focused": None,
        "skip": r"#\[ignore\b",
        "xfail": None,
        "focused": None,
        "assert": r"\bassert\w*!|\bpanic!|\bunreachable!",
        "sleep": r"\bsleep\s*\(",
        "mock": r"\bmock!\s*\{|\bautomock\b|\bMock\w+::new\s*\(|\.expect_\w+\s*\(",
        "incomplete": r"\b(?:todo|unimplemented)!",
        "mock_assert": r"\.expect_\w+\s*\(",
        "snapshot": r"(?:\binsta::)?assert_\w*snapshot!",
        "trivial_assert": r"\bassert!\(\s*(?:true|!\s*false)\s*\)",
        "broad_exception": r"#\[should_panic\s*\]|\bassert!\(\s*[\w.]+\.is_err\(\)\s*\)",
        "swallowed_error": r"\blet\s+_\s*=|^[ \t]*[^=\n]*\)\.ok\(\)[ \t]*;",
        "nondeterministic": r"\brand::(?:random|thread_rng|rng)\b|\bSystemTime::now\s*\(|\b(?:Utc|Local)::now\s*\(|\bUuid::new_v[47]\s*\(",
        "deterministic_guard": r"\b\w*Rng::(?:seed_from_u64|from_seed)\s*\(",
        "retry": None,
    },
    "java": {
        "globs": ["*Test.java", "*Tests.java"],
        "dir_globs": {},
        "require": None,
        "tests": [
            (
                r"^[ \t]*@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate|Property|RetryingTest|RepeatedIfExceptionsTest)\b(?:\((?:[^()\n]|\([^()\n]*\))*\))?",
                r"^[ \t]*(?:@[\w.]+(?:\((?:[^()\n]|\([^()\n]*\))*\))?[ \t]*)*(?:(?:public|protected|private|static|final|abstract|synchronized|default|native|strictfp)[ \t]+)*(?:<[^>\n]*>[ \t]+)?(?:void|byte|short|int|long|float|double|boolean|char|[A-Z][\w.]*(?:<[^()\n]*>)?(?:\[\])*)[ \t]+(?P<name>\w+)[ \t]*\(",
            ),
        ],
        "model": "brace",
        "brace": None,
        "prefix": r"^[ \t]*@",
        "empty_open": None,
        "group_skip": r"@(?:Disabled|Ignore)\b(?:\((?:[^()\"]|\"[^\"]*\")*\))?(?:\s*@[\w.]+(?:\((?:[^()\"]|\"[^\"]*\")*\))?)*\s*(?:(?:public|private|protected|static|final|abstract)\s+)*class\b",
        "group_focused": None,
        "skip": r"@Disabled\b|@Ignore\b|\bAssumptions?\.\w+\s*\(",
        "xfail": None,
        "focused": None,
        "assert": r"\bassert\w*\s*\(|\bverify\w*\s*\(|\bfail\s*\(|\bexpectThrows\s*\(",
        "sleep": r"\bThread\.sleep\s*\(|\bTimeUnit\.\w+\.sleep\s*\(",
        "mock": r"\bMockito\.\w+\s*\(|@Mock\b|\bmock\s*\(|\bwhen\s*\(|\bspy\s*\(|\bdoReturn\s*\(",
        "incomplete": r"\bthrow\s+new\s+UnsupportedOperationException\s*\(\s*\"(?i:[^\"]*(?:todo|not (?:yet )?implemented))|\bfail\s*\(\s*\"(?i:[^\"]*(?:todo|not (?:yet )?implemented))",
        "mock_assert": r"\bverify\w*\s*\(|\b(?:BDDMockito\.)?then\s*\([^()\n]*\)\s*\.\s*should\b",
        "snapshot": r"\bApprovals\.verify\w*\s*\(|\.toMatchSnapshot\s*\(",
        "trivial_assert": r"\b(?:Assertions\.)?assert(?:True\(\s*true|False\(\s*false)\s*\)|\bassertThat\(\s*(?:true|false)\s*\)\s*\.\s*is(?:True|False)\(\s*\)",
        "broad_exception": r"\bexpected\s*=\s*(?:java\.lang\.)?(?:Exception|RuntimeException|Throwable)\.class|\bassertThrows\(\s*(?:java\.lang\.)?(?:Exception|RuntimeException|Throwable)\.class",
        "swallowed_error": r"\bcatch\s*\([^()]*\)\s*\{\s*\}",
        "nondeterministic": r"\bMath\.random\s*\(|\bnew\s+Random\s*\(\s*\)|\bSystem\.currentTimeMillis\s*\(|\b(?:LocalDateTime|LocalDate|LocalTime|ZonedDateTime|Instant)\.now\s*\(\s*\)|\bUUID\.randomUUID\s*\(",
        "deterministic_guard": r"\bClock\.fixed\s*\(",
        "retry": r"@(?:RetryingTest|RepeatedIfExceptionsTest)\b",
    },
    "kotlin": {
        "globs": ["*Test.kt", "*Tests.kt"],
        "dir_globs": {},
        "require": None,
        "tests": [
            (
                r"^[ \t]*@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate|Property|RetryingTest|RepeatedIfExceptionsTest)\b(?:\((?:[^()\n]|\([^()\n]*\))*\))?",
                r"^[ \t]*(?:@[\w.]+(?:\((?:[^()\n]|\([^()\n]*\))*\))?[ \t]*)*(?:(?:public|private|protected|internal|override|suspend|open|inline|final)[ \t]+)*fun[ \t]+(?:<[^>\n]*>[ \t]+)?`?(?P<name>(?<=`)[^`\n]+|(?<!`)\w+)",
            ),
        ],
        "model": "brace",
        "brace": None,
        "prefix": r"^[ \t]*@",
        "empty_open": None,
        "group_skip": r"@(?:Disabled|Ignore)\b(?:\((?:[^()\"]|\"[^\"]*\")*\))?(?:\s*@[\w.]+(?:\((?:[^()\"]|\"[^\"]*\")*\))?)*\s*(?:(?:public|private|protected|internal|open|abstract|final|inner)\s+)*class\b",
        "group_focused": None,
        "skip": r"@Disabled\b|@Ignore\b|\bAssumptions?\.\w+\s*\(",
        "xfail": None,
        "focused": None,
        "assert": r"\bassert\w*\s*[(<]|\bshould[A-Z]\w*|\bfail\s*\(|\bexpectThat\s*\(",
        "sleep": r"\bThread\.sleep\s*\(|\bdelay\s*\(|\bTimeUnit\.\w+\.sleep\s*\(",
        "mock": r"\b(?:mockk|mock|spy|spyk|mockkStatic|mockkObject)\s*[<(]|\b(?:every|coEvery)\s*\{|\bwhenever\s*\(|\bMockito\.\w+\s*\(",
        "incomplete": r"\bTODO\s*\(",
        "mock_assert": r"\b(?:verify|coVerify|verifyAll|coVerifyAll|verifyOrder|coVerifyOrder|verifySequence|coVerifySequence)\s*[({]|\b(?:confirmVerified|coConfirmVerified)\s*\(",
        "snapshot": None,
        "trivial_assert": r"\bassertTrue\(\s*true\s*\)|\bassertFalse\(\s*false\s*\)|\btrue\s+shouldBe\s+true\b",
        "broad_exception": r"\b(?:assertThrows|assertFailsWith|shouldThrow)\s*<\s*(?:java\.lang\.)?(?:Exception|RuntimeException|Throwable)\s*>|\bshouldThrowAny\b|\bassertThrows\s*\(\s*(?:Exception|RuntimeException|Throwable)::class",
        "swallowed_error": r"\bcatch\s*\([^()]*\)\s*\{\s*\}",
        "nondeterministic": r"\bRandom\.next\w*\s*\(|\bSystem\.currentTimeMillis\s*\(|\b(?:LocalDateTime|LocalDate|LocalTime|ZonedDateTime|Instant)\.now\s*\(\s*\)|\bUUID\.randomUUID\s*\(|\bClock\.System\.now\s*\(",
        "deterministic_guard": r"\bClock\.fixed\s*\(",
        "retry": r"@(?:RetryingTest|RepeatedIfExceptionsTest)\b",
    },
    "csharp": {
        "globs": ["*Test.cs", "*Tests.cs"],
        "dir_globs": {},
        "require": None,
        "tests": [
            (
                r"^[ \t]*\[(?:Fact|Theory|Test|TestCase|TestCaseSource|TestMethod|DataTestMethod|SkippableFact|RetryFact)\b[^\]\n]*\]",
                r"^[ \t]*(?:\[[^\]\n]*\][ \t]*)*(?:(?:public|private|protected|internal|static|async|virtual|override|sealed|new|unsafe|extern)[ \t]+)*(?:void|Task(?:<[^()\n]*>)?|ValueTask(?:<[^()\n]*>)?)[ \t]+(?P<name>\w+)[ \t]*\(",
            ),
        ],
        "model": "brace",
        "brace": None,
        "prefix": r"^[ \t]*\[",
        "empty_open": None,
        "group_skip": r"\[(?:Ignore|Explicit)\b(?:\((?:[^()\"\n]|\"[^\"\n]*\")*\))?\]\s*(?:\[[^\]\n]*\]\s*)*(?:(?:public|internal|private|protected|static|sealed|abstract|partial)\s+)*class\b",
        "group_focused": None,
        "skip": r"[\[,]\s*(?:Ignore|Explicit)\b|\[\s*\w+\s*\([^\]\n]*\bSkip\s*=|\bSkip\.(?:If|IfNot|Unless)\s*\(|\bAssert\.Ignore\s*\(",
        "xfail": None,
        "focused": None,
        "assert": r"\b(?:Assert|CollectionAssert|StringAssert|FileAssert|DirectoryAssert)\.\w+|\.Should\w*\b",
        "sleep": r"\bThread\.Sleep\s*\(|\bTask\.Delay\s*\(",
        "mock": r"\bnew\s+Mock<|\bMock\.Of<|\bSubstitute\.For<|\bA\.Fake<|\.Setup\w*\s*\(",
        "incomplete": r"\bAssert\.Inconclusive\s*\(|\bthrow\s+new\s+NotImplementedException\b",
        "mock_assert": r"\.Verify\w*\s*\(|\.(?:Received|DidNotReceive|ReceivedWithAnyArgs|DidNotReceiveWithAnyArgs)\s*\(|\.Must(?:Not)?HaveHappened\w*",
        "snapshot": r"(?<![\w.])Verify\w*\s*\(|\.(?:Should)?MatchSnapshot\s*\(|\.ShouldMatchSnapshot\s*\(",
        "trivial_assert": r"\bAssert\.(?:True|IsTrue)\(\s*true\s*\)|\bAssert\.(?:False|IsFalse)\(\s*false\s*\)|\b(?:true|false)\.Should\(\)\.Be(?:True|False)\(\s*\)",
        "broad_exception": r"\bAssert\.Throws(?:Any)?(?:Async)?\s*<\s*(?:System\.)?Exception\s*>|\[ExpectedException\(\s*typeof\(\s*(?:System\.)?Exception\s*\)|\.Should\(\)\.Throw(?:Async)?\s*<\s*(?:System\.)?Exception\s*>",
        "swallowed_error": r"\bcatch\s*(?:\([^()]*\))?\s*\{\s*\}",
        "nondeterministic": r"\bDateTime(?:Offset)?\.(?:Now|UtcNow|Today)\b|\bGuid\.NewGuid\s*\(|\bnew\s+Random\s*\(\s*\)|\bRandom\.Shared\b",
        "deterministic_guard": r"\bnew\s+FakeTimeProvider\s*\(",
        "retry": r"[\[,]\s*Retry\w*\b",
    },
    "swift": {
        "globs": ["*Tests.swift", "*Test.swift"],
        "dir_globs": {},
        "require": r"\bimport\s+(?:XCTest|Testing)\b",
        "tests": [
            (
                r"^[ \t]*(?:@\w+(?:\((?:[^()\n]|\([^()\n]*\))*\))?[ \t]+)*(?:(?:public|private|fileprivate|internal|open|final|override|static|nonisolated)[ \t]+)*func[ \t]+(?P<name>test\w*)[ \t]*[(<]",
                None,
            ),
            (
                r"^[ \t]*@Test\b(?:\((?:[^()\n]|\([^()\n]*\))*\))?",
                r"^[ \t]*(?:@\w+(?:\((?:[^()\n]|\([^()\n]*\))*\))?[ \t]*)*(?:(?:public|private|fileprivate|internal|open|final|override|static|nonisolated)[ \t]+)*func[ \t]+(?P<name>\w+)[ \t]*[(<]",
            ),
        ],
        "model": "brace",
        "brace": None,
        "prefix": r"^[ \t]*@",
        "empty_open": None,
        "group_skip": r"@Suite\s*\((?:[^()\n]|\([^()\n]*\))*\.disabled\b(?:[^()\n]|\([^()\n]*\))*\)\s*(?:(?:public|private|fileprivate|internal|final)\s+)*(?:struct|class|actor)\b",
        "group_focused": None,
        "skip": r"\bXCTSkip\w*\s*\(|^[ \t]*@Test\b[^\n]*?\.(?:disabled|enabled)\s*\(",
        "xfail": r"\bXCTExpectFailure\s*\(|\bwithKnownIssue\b",
        "focused": None,
        "assert": r"\bXCT(?:Assert\w*|Fail|Unwrap)\b|#(?:expect|require)\b",
        "sleep": r"\busleep\s*\(|\bsleep\s*\(",
        "mock": r"\bMock\w*\s*\(|\bstub\s*\(|\bgiven\s*\(",
        "incomplete": None,
        "mock_assert": r"\bverify\s*\(",
        "snapshot": r"\bassert(?:Inline)?Snapshots?\s*\(",
        "trivial_assert": r"\bXCTAssert(?:True)?\(\s*true\s*\)|\bXCTAssertFalse\(\s*false\s*\)|#expect\(\s*true\s*\)",
        "broad_exception": r"\bXCTAssertThrowsError\s*\((?:[^()\n]|\([^()\n]*\))*\)[ \t]*(?:$|//)|#expect\(\s*throws:\s*(?:\(\s*any\s+Error\s*\)|Error)\.self",
        "swallowed_error": r"\btry\?|\bcatch\s*\{\s*\}",
        "nondeterministic": r"\bDate\s*\(\s*\)|\bDate\.now\b|\bUUID\s*\(\s*\)|\.random\s*\(\s*in\b|\.randomElement\s*\(|\.shuffled\s*\(",
        "deterministic_guard": None,
        "retry": None,
    },
    "php": {
        "globs": ["*Test.php"],
        "dir_globs": {},
        "require": None,
        "tests": [
            (r"^[ \t]*(?:(?:public|protected|private|static|final)[ \t]+)*function[ \t]+(?P<name>test\w*)[ \t]*\(", None),
            (
                r"^[ \t]*(?:#\[Test\]|/\*\*[^\n]*@test\b|\*[ \t]*@test\b)",
                r"^[ \t]*(?:#\[[^\]\n]*\][ \t]*)*(?:(?:public|protected|private|static|final)[ \t]+)*function[ \t]+(?P<name>\w+)[ \t]*\(",
            ),
            (r"^[ \t]*(?:it|test)[ \t]*\([ \t]*(?P<q>['\"])(?P<name>.*?)(?P=q)", None),
        ],
        "model": "brace",
        "brace": None,
        "prefix": r"^[ \t]*(?:#\[|/\*\*|\*)",
        "empty_open": None,
        "group_skip": None,
        "group_focused": None,
        "skip": r"\bmarkTestSkipped\s*\(|->skip\s*\(",
        "xfail": None,
        "focused": r"->only\s*\(",
        "assert": r"(?:\$this->|self::|static::)assert\w*\s*\(|(?<![\w$>:])expect\s*\(|(?:\$this->|self::|static::)expectException\w*\s*\(|(?:\$this->|self::|static::)fail\s*\(",
        "sleep": r"(?<![\w$>:])u?sleep\s*\(",
        "mock": r"->(?:createMock|createStub|createConfiguredMock|createPartialMock|getMockBuilder|prophesize)\s*\(|\bMockery::mock\s*\(",
        "incomplete": r"\bmarkTestIncomplete\s*\(|->todo\s*\(",
        "mock_assert": r"->(?:expects|shouldReceive|shouldHaveReceived|shouldNotReceive|shouldNotHaveReceived)\s*\(",
        "snapshot": r"(?<![\w$>:])expect\s*\([^\n;]*?\)\s*->\s*toMatch\w*Snapshot\s*\(|(?:\$this->|self::|static::)assert\w*Snapshot\w*\s*\(",
        "trivial_assert": r"(?:\$this->|self::|static::)assert(?:True\(\s*true|False\(\s*false)\s*\)|\bexpect\(\s*(?:true|false)\s*\)->toBe(?:True|False)\(\s*\)",
        "broad_exception": r"\bexpectException\(\s*\\?(?:Exception|Throwable)::class|->toThrow\(\s*\\?(?:Exception|Throwable)::class",
        "swallowed_error": r"\bcatch\s*\([^()]*\)\s*\{\s*\}",
        "nondeterministic": r"(?<![\w$>:])(?:time|rand|mt_rand|random_int|uniqid|microtime)\s*\(|\bnew\s+\\?DateTime(?:Immutable)?\s*\(\s*\)|\bCarbon::(?:now|today)\s*\(",
        "deterministic_guard": r"\bCarbon::setTestNow\s*\(|\b(?:mt_)?srand\s*\(|\bClockMock::register\s*\(",
        "retry": r"@retry\b|#\[Retry\b",
    },
    "ruby": {
        "globs": ["*_spec.rb", "test_*.rb", "*_test.rb"],
        "dir_globs": {},
        "require": None,
        "tests": [
            (r"^[ \t]*(?:x|f)?(?:it|specify|example|scenario)\b[ \t]*\(?[ \t]*(?P<q>[\"'])(?P<name>.*?)(?P=q)", None),
            (r"^[ \t]*test\b[ \t]*\(?[ \t]*(?P<q>[\"'])(?P<name>.*?)(?P=q)", None),
            (r"^[ \t]*def[ \t]+(?P<name>test_\w+)", None),
        ],
        "model": "indent",
        "brace": None,
        "prefix": None,
        "empty_open": r"\bdo[ \t]*(?:\|[^|\n]*\|)?[ \t]*(?:#.*)?$|^[ \t]*def\b",
        "group_skip": r"^[ \t]*(?:xdescribe|xcontext)\b|^[ \t]*(?:describe|context)\b[^\n]*,[ \t]*skip:",
        "group_focused": r"^[ \t]*(?:fdescribe|fcontext)\b|^[ \t]*(?:describe|context)\b[^\n]*(?:,[ \t]*focus:[ \t]*true|,[ \t]*:focus\b)",
        "skip": r"^[ \t]*x(?:it|specify|example|scenario)\b|^[ \t]*skip\b|,[ \t]*skip:",
        "xfail": r"^[ \t]*pending\b|,[ \t]*pending:",
        "focused": r"^[ \t]*f(?:it|specify|example|scenario)\b|,[ \t]*focus:[ \t]*true|,[ \t]*:focus\b",
        "assert": r"\bexpect\s*[({]|\bis_expected\b|\.should(?:_not)?\b|^[ \t]*(?:assert|refute)\w*|\.must_\w+|\.wont_\w+|^[ \t]*flunk\b",
        "sleep": r"(?<![\w.:])sleep\b",
        "mock": r"(?<![\w.:])(?:double|instance_double|class_double|object_double|spy)\s*[(\"']|\ballow\s*\([^\n]*?\)\s*\.to\s+receive|\bMinitest::Mock\.new\b|\bMock\.new\b",
        "incomplete": r"^[ \t]*(?:x|f)?(?:it|specify|example|scenario)\b[ \t]*\(?[ \t]*(?:\"[^\"\n]*\"|'[^'\n]*')[ \t]*\)?[ \t]*(?:#.*)?$|\braise\s+NotImplementedError\b",
        "mock_assert": r"\bexpect\s*\([^\n;]*?\)\s*\.(?:to|not_to|to_not)\s+(?:receive|have_received)\b[^\n]*|\b\w*mock\w*\.verify\b",
        "snapshot": r"\bexpect\s*[({][^\n;]*?\.(?:to|not_to|to_not)\s+match_\w*snapshot\w*|\bassert_matches?_\w*snapshot\w*",
        "trivial_assert": r"\bexpect\(\s*true\s*\)\.to\s+(?:be\(\s*true\s*\)|be_truthy|eq\(\s*true\s*\))|^[ \t]*assert\s*\(?\s*true\b",
        "broad_exception": r"\.to\s+raise_error[ \t]*(?:$|[{;.]|do\b)|\b(?:raise_error|assert_raises)\(\s*(?:StandardError|Exception)\s*\)|\bassert_raises[ \t]*(?:$|[{;]|do\b)",
        "swallowed_error": r"^[ \t]*rescue\b[^\n]*\n[ \t]*end\b|\brescue\s+nil\b",
        "nondeterministic": r"\b(?:Time|DateTime)\.now\b|\bDate\.today\b|(?<![\w.])rand\b|\bSecureRandom\.\w+|\.(?:sample|shuffle)\b",
        "deterministic_guard": r"\btravel_to\b|\bfreeze_time\b|\bTimecop\.(?:freeze|travel)\b|\bsrand\s*\(",
        "retry": r",[ \t]*retry:|:retry\b",
    },
    "cpp": {
        "globs": [
            "*_test.cc", "*_test.cpp", "*_test.cxx", "*_unittest.cc", "*_unittest.cpp",
            "test_*.cc", "test_*.cpp", "*Test.cpp", "*Tests.cpp",
        ],
        "dir_globs": {},
        "require": r"\b(?:TEST|TEST_F|TEST_P|TYPED_TEST|TYPED_TEST_P|TEST_CASE|TEST_CASE_METHOD|SCENARIO)\(",
        "tests": [
            (r"^[ \t]*(?:TEST|TEST_F|TEST_P|TYPED_TEST|TYPED_TEST_P)[ \t]*\([ \t]*(?P<prefix>\w+)[ \t]*,[ \t]*(?P<name>\w+)", None),
            (r"^[ \t]*(?:TEST_CASE|SCENARIO)[ \t]*\([ \t]*\"(?P<name>[^\"\n]*)\"", None),
            (r"^[ \t]*TEST_CASE_METHOD[ \t]*\([ \t]*\w+[ \t]*,[ \t]*\"(?P<name>[^\"\n]*)\"", None),
        ],
        "model": "brace",
        "brace": None,
        "prefix": None,
        "empty_open": None,
        "group_skip": None,
        "group_focused": None,
        "skip": r"\b(?:TYPED_)?TEST\w*\s*\([^()\n]*\bDISABLED_|\bGTEST_SKIP\s*\(|\b(?:TEST_CASE|SCENARIO|TEST_CASE_METHOD)\b[^\n]*\"[^\"\n]*\[(?:\.|!hide\])|\bdoctest::skip\s*\(",
        "xfail": r"\b(?:TEST_CASE|SCENARIO|TEST_CASE_METHOD)\b[^\n]*\"[^\"\n]*\[!(?:shouldfail|mayfail)\]|\bdoctest::(?:should_fail|may_fail)\s*\(",
        "focused": None,
        "assert": r"\b(?:EXPECT|ASSERT)_\w+\s*\(|\b(?:REQUIRE|CHECK)(?:_\w+)?\s*\(|\b(?:FAIL|ADD_FAILURE|ADD_FAILURE_AT|SUCCEED|FAIL_CHECK)\s*\(",
        "sleep": r"\bstd::this_thread::sleep_(?:for|until)\s*\(|(?<![\w.:>])u?sleep\s*\(",
        "mock": r"\bMOCK_METHOD\w*\s*\(|\bEXPECT_CALL\s*\(|\bON_CALL\s*\(|\b(?:Nice|Strict|Naggy)Mock\s*<",
        "incomplete": None,
        "mock_assert": r"\bEXPECT_CALL\s*\(",
        "snapshot": r"\bApprovals::verify\w*\s*\(",
        "trivial_assert": r"\b(?:EXPECT|ASSERT)_TRUE\s*\(\s*true\s*\)|\b(?:EXPECT|ASSERT)_FALSE\s*\(\s*false\s*\)|\b(?:REQUIRE|CHECK)\s*\(\s*true\s*\)|\b(?:REQUIRE|CHECK)_FALSE\s*\(\s*false\s*\)|\bSUCCEED\s*\(",
        "broad_exception": r"\b(?:EXPECT|ASSERT)_ANY_THROW\s*\(|\b(?:REQUIRE|CHECK)_THROWS\s*\(|\b(?:EXPECT|ASSERT)_THROW\s*\([^\n]*,\s*(?:std::)?exception\s*\)",
        "swallowed_error": r"\bcatch\s*\([^()]*\)\s*\{\s*\}",
        "nondeterministic": r"(?<![\w.>])(?:std::)?rand\s*\(\s*\)|\bstd::random_device\b|(?<![\w.:>])time\s*\(\s*(?:nullptr|NULL|0)\s*\)|\bstd::chrono::(?:system|high_resolution)_clock::now\s*\(",
        "deterministic_guard": r"\bsrand\s*\(",
        "retry": None,
    },
}
LANGUAGE_ORDER = ("python", "javascript", "go", "rust", "java", "kotlin", "csharp", "swift", "php", "ruby", "cpp")
FLAG_NAMES = (
    "skip", "xfail", "focused", "no_assert", "empty", "sleep", "heavy_mock", "duplicate_name",
    "trivial_assert", "mock_only_assert", "snapshot_only", "broad_exception", "swallowed_error",
    "nondeterministic", "retry", "incomplete",
)


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


def classify(rel: Path, text_loader) -> str | None:
    name = rel.name
    for language in LANGUAGE_ORDER:
        spec = LANGUAGES[language]
        matched = any(fnmatch.fnmatchcase(name, glob) for glob in spec["globs"])
        if not matched:
            matched = any(
                directory in rel.parts[:-1] and any(fnmatch.fnmatchcase(name, glob) for glob in globs)
                for directory, globs in spec["dir_globs"].items()
            )
        if not matched:
            continue
        if spec["require"] and not re.search(spec["require"], text_loader()):
            continue
        return language
    return None


def find_files(root: Path) -> list:
    found = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(current) / name
            if path.is_file():
                found.append(path.relative_to(root))
    return sorted(found, key=lambda p: p.as_posix())


@functools.lru_cache(maxsize=None)
def rx(pattern: str):
    return re.compile(pattern, re.M)


def count(pattern, text: str) -> int:
    return len(rx(pattern).findall(text)) if pattern else 0


def has_match(pattern, text: str) -> bool:
    return bool(pattern) and rx(pattern).search(text) is not None


def signal_flags(language: str, body: str, file_text: str) -> set:
    spec = LANGUAGES[language]
    flags = set()
    for flag, key in (
        ("skip", "skip"), ("xfail", "xfail"), ("focused", "focused"), ("sleep", "sleep"),
        ("incomplete", "incomplete"), ("trivial_assert", "trivial_assert"),
        ("broad_exception", "broad_exception"), ("swallowed_error", "swallowed_error"),
        ("retry", "retry"),
    ):
        if has_match(spec[key], body):
            flags.add(flag)
    if has_match(spec["nondeterministic"], body) and not has_match(spec["deterministic_guard"], file_text):
        flags.add("nondeterministic")
    snapshots = count(spec["snapshot"], body)
    rest = rx(spec["snapshot"]).sub(" ", body) if spec["snapshot"] else body
    mocks = count(spec["mock_assert"], rest)
    rest = rx(spec["mock_assert"]).sub(" ", rest) if spec["mock_assert"] else rest
    asserts = count(spec["assert"], rest)
    if not (snapshots or mocks or asserts):
        flags.add("no_assert")
    elif snapshots and not mocks and not asserts:
        flags.add("snapshot_only")
    elif mocks and not snapshots and not asserts:
        flags.add("mock_only_assert")
    if count(spec["mock"], body) >= HEAVY_MOCK_THRESHOLD:
        flags.add("heavy_mock")
    return flags


def decorator_flags(text: str, nodes) -> set:
    spec = LANGUAGES["python"]
    flags = set()
    for node in nodes:
        source = ast.get_source_segment(text, node) or ""
        if has_match(spec["skip"], source):
            flags.add("skip")
        if has_match(spec["xfail"], source):
            flags.add("xfail")
    return flags


def python_tests(text: str) -> list:
    tree = ast.parse(text)
    lines = text.splitlines()
    tests = []

    def visit(statements, inherited):
        for node in statements:
            if isinstance(node, ast.ClassDef):
                visit(node.body, inherited | decorator_flags(text, node.decorator_list))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                first = min([node.lineno] + [d.lineno for d in node.decorator_list])
                body = "\n".join(lines[first - 1:node.end_lineno])
                flags = signal_flags("python", body, text) | inherited
                if all(
                    isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                    for s in node.body
                ):
                    flags.add("empty")
                tests.append({"name": node.name, "line": node.lineno, "flags": flags})

    module_flags = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            module_flags |= decorator_flags(text, [node])
    visit(tree.body, module_flags)
    return tests


def find_block(text: str, search_from: int, opener) -> tuple:
    if opener:
        match = rx(opener).search(text, search_from)
        open_at = match.end() - 1 if match else -1
    else:
        open_at = text.find("{", search_from)
    if open_at < 0:
        return None, None
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return open_at, index
    return open_at, None


def find_starts(spec: dict, lines: list) -> list:
    alternatives = [(rx(start), rx(name) if name else None) for start, name in spec["tests"]]
    by_name_line = {}
    for index, line in enumerate(lines):
        for start_re, name_re in alternatives:
            match = start_re.search(line)
            if not match:
                continue
            groups = match.groupdict()
            if name_re is None:
                name, name_line, name_col = groups["name"], index, match.end()
                if groups.get("prefix"):
                    name = f"{groups['prefix']}.{name}"
            else:
                resolved = None
                for ahead in range(index, min(len(lines), index + 1 + BODY_TEST_LOOKAHEAD)):
                    base = match.end() if ahead == index else 0
                    name_match = name_re.search(lines[ahead][base:])
                    if name_match:
                        resolved = (name_match.group("name"), ahead, base + name_match.end())
                        break
                if resolved is None:
                    continue
                name, name_line, name_col = resolved
            known = by_name_line.get(name_line)
            if known is None or index < known["start"]:
                by_name_line[name_line] = {
                    "start": index, "start_col": match.end(), "name": name,
                    "name_line": name_line, "name_col": name_col,
                }
    return sorted(by_name_line.values(), key=lambda t: (t["start"], t["name_line"]))


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def closes_block(stripped: str) -> bool:
    if stripped.startswith("}"):
        return True
    return stripped.startswith("end") and not (stripped[3:4].isalnum() or stripped[3:4] == "_")


def indent_end(lines: list, first: int, clamp: int) -> int:
    base = indent_of(lines[first])
    for index in range(first + 1, clamp):
        if lines[index].strip() and indent_of(lines[index]) <= base:
            return index + 1 if closes_block(lines[index].strip()) else index
    return clamp


def indent_is_empty(spec: dict, lines: list, name_line: int, clamp: int) -> bool:
    if not has_match(spec["empty_open"], lines[name_line]):
        return False
    for index in range(name_line + 1, clamp):
        if lines[index].strip():
            stripped = lines[index].split("#")[0].strip()
            return stripped == "end" and indent_of(lines[index]) == indent_of(lines[name_line])
    return False


def group_ranges(spec: dict, key: str, lines: list, joined: str) -> list:
    pattern = spec[key]
    if not pattern:
        return []
    if spec["model"] == "indent":
        return [
            (index + 1, indent_end(lines, index, len(lines)))
            for index, line in enumerate(lines) if has_match(pattern, line)
        ]
    ranges = []
    for match in rx(pattern).finditer(joined):
        open_at, close_at = find_block(joined, match.end(), spec["brace"])
        if open_at is not None:
            ranges.append((open_at, len(joined) if close_at is None else close_at))
    return ranges


def body_end(spec: dict, lines: list, offsets: list, test: dict, first: int, clamp: int) -> tuple:
    if spec["model"] == "indent":
        return (
            min(indent_end(lines, test["name_line"], clamp), clamp),
            indent_is_empty(spec, lines, test["name_line"], clamp),
        )
    segment = "\n".join(lines[first:clamp])
    name_at = offsets[test["name_line"]] - offsets[first] + test["name_col"]
    open_at, close_at = find_block(segment, name_at, spec["brace"])
    if open_at is None:
        return clamp, False
    if close_at is None:
        return clamp, segment[open_at + 1:].strip() == ""
    return first + segment.count("\n", 0, close_at) + 1, segment[open_at + 1:close_at].strip() == ""


def generic_tests(language: str, text: str) -> list:
    spec = LANGUAGES[language]
    lines = text.splitlines()
    joined = "\n".join(lines)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    starts = find_starts(spec, lines)
    prefix_re = rx(spec["prefix"]) if spec["prefix"] else None
    for test in starts:
        first = test["start"]
        while prefix_re and first > 0 and prefix_re.search(lines[first - 1]):
            first -= 1
        test["first"] = first
    ends = []
    for _ in range(2):
        firsts = sorted({t["first"] for t in starts})
        ends = []
        for test in starts:
            later = bisect.bisect_right(firsts, test["first"])
            clamp = max(firsts[later] if later < len(firsts) else len(lines), test["name_line"] + 1)
            ends.append(body_end(spec, lines, offsets, test, test["first"], clamp))
        # A prefix line that is the tail of the previous test (one-line tests) is not this test's prefix.
        for index in range(1, len(starts)):
            floor = min(ends[index - 1][0], starts[index]["start"])
            starts[index]["first"] = max(starts[index]["first"], floor)
    groups = [(flag, group_ranges(spec, key, lines, joined)) for flag, key in (("skip", "group_skip"), ("focused", "group_focused"))]
    tests = []
    for test, (end, empty) in zip(starts, ends):
        flags = signal_flags(language, "\n".join(lines[test["first"]:end]), text)
        if empty:
            flags.add("empty")
        position = test["start"] if spec["model"] == "indent" else offsets[test["start"]] + test["start_col"]
        for flag, ranges in groups:
            if any(low <= position < high for low, high in ranges):
                flags.add(flag)
        tests.append({"name": test["name"], "line": test["name_line"] + 1, "flags": flags})
    return tests


def extract_tests(language: str, text: str) -> list:
    tests = python_tests(text) if language == "python" else generic_tests(language, text)
    names = [t["name"] for t in tests]
    for test in tests:
        if names.count(test["name"]) > 1:
            test["flags"].add("duplicate_name")
        test["flags"] = sorted(test["flags"])
    return sorted(tests, key=lambda t: (t["line"], t["name"]))


def run_git(root: Path, args: list) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def harness_install_time(root: Path) -> int | None:
    out = run_git(root, ["log", "--diff-filter=A", "--format=%ct", "--", ":(top,literal).harness/VERSION"])
    if not out:
        return None
    times = [int(line) for line in out.split() if line.isdigit()]
    return min(times) if times else None


def commit_info(root: Path, rel: str) -> tuple:
    out = run_git(root, ["log", "-1", "--format=%ct %cI", "--", f":(literal){rel}"])
    if not out or not out.strip():
        return None, None
    stamp, _, iso = out.strip().partition(" ")
    return (int(stamp), iso) if stamp.isdigit() and iso else (None, None)


def runner_candidates(root: Path, has_python_tests: bool) -> list:
    found = []
    pytest_evidence = None
    if (root / "pytest.ini").is_file():
        pytest_evidence = "pytest.ini"
    elif (root / "conftest.py").is_file():
        pytest_evidence = "conftest.py"
    elif (root / "pyproject.toml").is_file() and "[tool.pytest" in read_text(root / "pyproject.toml"):
        pytest_evidence = "pyproject.toml [tool.pytest"
    if pytest_evidence:
        found.append({"runner": "pytest", "command": "pytest", "evidence": pytest_evidence})
    elif has_python_tests:
        found.append({
            "runner": "unittest",
            "command": "python3 -m unittest discover",
            "evidence": "python test files without pytest configuration",
        })
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(read_text(package)).get("scripts")
        except (ValueError, AttributeError):
            scripts = None
        if isinstance(scripts, dict) and "test" in scripts:
            found.append({"runner": "npm", "command": "npm test", "evidence": "package.json scripts.test"})
    for marker, runner, command in (
        ("go.mod", "go", "go test ./..."),
        ("Cargo.toml", "cargo", "cargo test"),
        ("pom.xml", "maven", "mvn test"),
    ):
        if (root / marker).is_file():
            found.append({"runner": runner, "command": command, "evidence": marker})
    for marker in ("build.gradle", "build.gradle.kts"):
        if (root / marker).is_file():
            wrapper = (root / "gradlew").is_file()
            found.append({
                "runner": "gradle",
                "command": "./gradlew test" if wrapper else "gradle test",
                "evidence": marker + (", gradlew" if wrapper else ""),
            })
            break
    solution = sorted(p.name for p in root.iterdir() if p.is_file() and p.suffix in (".sln", ".csproj"))
    if solution:
        found.append({"runner": "dotnet", "command": "dotnet test", "evidence": solution[0]})
    if (root / ".rspec").is_file():
        found.append({"runner": "rspec", "command": "bundle exec rspec", "evidence": ".rspec"})
    elif (root / "Gemfile").is_file() and (root / "spec").is_dir():
        found.append({"runner": "rspec", "command": "bundle exec rspec", "evidence": "Gemfile, spec/"})
    if (root / "Rakefile").is_file() and (root / "test").is_dir():
        found.append({"runner": "rake", "command": "bundle exec rake test", "evidence": "Rakefile, test/"})
    if (root / "Package.swift").is_file():
        found.append({"runner": "swift", "command": "swift test", "evidence": "Package.swift"})
    for marker in ("phpunit.xml", "phpunit.xml.dist"):
        if (root / marker).is_file():
            found.append({"runner": "phpunit", "command": "vendor/bin/phpunit", "evidence": marker})
            break
    composer = root / "composer.json"
    if composer.is_file():
        try:
            composer_scripts = json.loads(read_text(composer)).get("scripts")
        except (ValueError, AttributeError):
            composer_scripts = None
        if isinstance(composer_scripts, dict) and "test" in composer_scripts:
            found.append({"runner": "composer", "command": "composer test", "evidence": "composer.json scripts.test"})
    if (root / "CMakeLists.txt").is_file():
        found.append({"runner": "ctest", "command": "ctest --test-dir build", "evidence": "CMakeLists.txt"})
    return found


def scan(root: Path) -> dict:
    root = Path(root)
    harness_time = harness_install_time(root)
    files = []
    inventory = []
    flag_totals = {}
    for rel in find_files(root):
        path = root / rel
        cache = []

        def load(path=path, cache=cache):
            if not cache:
                cache.append(read_text(path))
            return cache[0]

        try:
            language = classify(rel, load)
        except OSError:
            continue
        if language is None:
            if any(part in INVENTORY_DIRS for part in rel.parts[:-1]):
                inventory.append(rel.as_posix())
            continue
        parse_error = False
        try:
            tests = extract_tests(language, load())
        except OSError:
            continue
        except (SyntaxError, ValueError, RecursionError):
            tests, parse_error = [], True
        commit_time, last_commit = commit_info(root, rel.as_posix())
        predates = None if commit_time is None or harness_time is None else commit_time < harness_time
        for test in tests:
            for flag in test["flags"]:
                flag_totals[flag] = flag_totals.get(flag, 0) + 1
        files.append({
            "path": rel.as_posix(),
            "language": language,
            "last_commit": last_commit,
            "predates_harness": predates,
            "parse_error": parse_error,
            "tests": tests,
        })
    return {
        "root": str(root),
        "runner_candidates": runner_candidates(root, any(f["language"] == "python" for f in files)),
        "files": files,
        "inventory": sorted(inventory),
        "summary": {
            "files": len(files),
            "tests": sum(len(f["tests"]) for f in files),
            "flags": {flag: flag_totals[flag] for flag in sorted(flag_totals)},
        },
    }


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="test_scan.py")
    parser.add_argument("path", nargs="?", default=".")
    args = parser.parse_args(argv)
    root = Path(args.path)
    if not root.is_dir():
        print(f"test_scan: {args.path} is not an existing directory", file=sys.stderr)
        return 2
    print(json.dumps(scan(root), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
