"""0.1.41: the API's additive "calibrated" field is read into Answer.calibrated; the plain fields are untouched."""
from ekbasis import Answer, Calibrated


def test_yes_no_with_calibrated():
    a = Answer.from_api({"type": "noul", "noul": 0.9859, "probability": 0.9859, "value": True, "confidence": 0.9859,
                         "calibrated": {"temperature": 1.55, "confidence": 0.9395, "probability": 0.9395}})
    assert a.p_yes == 0.9859 and a.confidence == 0.9859 and a.value is True  # raw, as before
    assert isinstance(a.calibrated, Calibrated)
    assert a.calibrated.p_yes == 0.9395 and a.calibrated.temperature == 1.55
    assert abs(a.calibrated.probabilities["no"] - 0.0605) < 1e-9


def test_choice_with_calibrated():
    a = Answer.from_api({"type": "choice", "choice": "b", "probabilities": {"a": 0.01, "b": 0.99}, "confidence": 0.99,
                         "calibrated": {"temperature": 1.55, "confidence": 0.95, "probabilities": {"a": 0.05, "b": 0.95}}})
    assert a.value == "b" and a.confidence == 0.99
    assert a.calibrated.probabilities == {"a": 0.05, "b": 0.95} and a.calibrated.p_yes is None


def test_older_server_without_calibrated():
    a = Answer.from_api({"type": "noul", "probability": 0.2, "value": False, "confidence": 0.8})
    assert a.calibrated is None and a.p_yes == 0.2
    b = Answer.from_api({"type": "noul", "probability": 0.2, "value": False, "confidence": 0.8, "calibrated": None})
    assert b.calibrated is None
