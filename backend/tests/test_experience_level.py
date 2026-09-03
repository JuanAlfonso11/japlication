from app.services import experience_level


def test_infer_detects_each_level_from_title():
    assert experience_level.infer("Backend Intern") == "internship"
    assert experience_level.infer("Junior Backend Engineer") == "entry"
    assert experience_level.infer("Mid-level Backend Engineer") == "mid"
    assert experience_level.infer("Senior Backend Engineer") == "senior"
    assert experience_level.infer("Engineering Manager") == "lead"


def test_infer_returns_none_when_unclassifiable():
    assert experience_level.infer("Backend Engineer") is None
    assert experience_level.infer(None, "") is None


def test_infer_joins_multiple_text_fields():
    assert experience_level.infer("Backend Engineer", "We need a senior candidate") == "senior"


def test_normalize_native_handles_jobicy_midweight():
    assert experience_level.normalize_native("Midweight") == "mid"
    assert experience_level.normalize_native("Senior") == "senior"
    assert experience_level.normalize_native(None) is None


def test_to_muse_and_to_himalayas_mappings():
    assert experience_level.to_muse("senior") == "Senior Level"
    assert experience_level.to_muse("internship") == "Internship"
    assert experience_level.to_himalayas("lead") == "Manager,Director,Executive"
    assert experience_level.to_himalayas("entry") == "Entry-level"


def test_matches_treats_unknown_level_as_a_pass():
    assert experience_level.matches(None, "senior") is True
    assert experience_level.matches("senior", None) is True
    assert experience_level.matches("senior", "senior") is True
    assert experience_level.matches("entry", "senior") is False
