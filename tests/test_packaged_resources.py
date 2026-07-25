from evozeus_session_signal_skill.resources import factors_root, source_checkout_root, templates_root


def test_source_checkout_root_contains_official_factors_and_templates():
    root = source_checkout_root()

    assert (root / "factors" / "semantic-phrase-clusters" / "FACTOR.xml").is_file()
    assert (root / "factors" / "semantic-phrase-clusters" / "factor.py").is_file()
    assert (root / "templates" / "ai-usage-profile-report" / "index.html").is_file()
    assert (root / "templates" / "ai-usage-profile-report" / "report-data-contract.md").is_file()


def test_resource_helpers_return_existing_roots():
    assert factors_root().is_dir()
    assert templates_root().is_dir()
