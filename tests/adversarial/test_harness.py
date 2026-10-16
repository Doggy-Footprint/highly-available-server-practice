from pathlib import Path


def test_adversarial_harness_ready() -> None:
    assert Path("docs/designs/_template.md").is_file()
    assert Path("reports/_review_template.md").is_file()
    assert Path("docs/reference/solution-guide.md").is_file()
