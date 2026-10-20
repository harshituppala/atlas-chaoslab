from chaoslab.recovery import evaluate


def test_recovery_scorer_rejects_missing_fields_and_boolean_counter():
    assert evaluate({"results": 1}, {"results": True}) == {"results": False}
    assert evaluate({"status": "succeeded"}, {}) == {"status": False}
    assert evaluate({"status": "succeeded"}, {"status": "failed"}) == {"status": False}
