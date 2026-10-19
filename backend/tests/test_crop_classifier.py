from app.ml.crop_classifier import apply_prior, classify


def test_flooded_kharif_season_is_paddy():
    feats = {"season_days": 130, "peak_ndvi": 0.8, "flood_signal_db": 6.0}
    crop, conf, alts = classify(feats, sowing_month=7)
    assert crop == "paddy" and conf >= 0.6
    assert len(alts) == 3 and alts[0]["p"] <= conf


def test_short_rabi_season_is_pulses():
    crop, conf, _ = classify({"season_days": 80, "peak_ndvi": 0.55, "flood_signal_db": 0.0}, sowing_month=12)
    assert crop == "pulses" and conf >= 0.6


def test_ambiguous_season_is_uncertain():
    # 110-day unflooded kharif crop with mid greenness: maize or paddy (radar may have missed puddling)
    _, conf, _ = classify({"season_days": 110, "peak_ndvi": 0.7, "flood_signal_db": 0.0}, sowing_month=7)
    assert conf < 0.6


def test_district_prior_shifts_probabilities():
    probs = {"paddy": 0.5, "maize": 0.5}
    out = apply_prior(probs, {"paddy": 0.9, "maize": 0.1})
    assert out["paddy"] > out["maize"]
    assert abs(sum(out.values()) - 1) < 1e-9
    assert apply_prior(probs, {}) == probs
