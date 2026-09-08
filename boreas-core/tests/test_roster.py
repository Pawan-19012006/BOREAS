from boreas_core.vessels.roster import ROSTER, get_vessel_by_id


def test_roster_has_multiple_active_vessels():
    active = [v for v in ROSTER if v.active]
    assert len(active) >= 2


def test_roster_entries_have_required_fields():
    for vessel in ROSTER:
        assert vessel.id
        assert vessel.name
        assert vessel.vessel_type
        assert vessel.home_port
        assert len(vessel.home_port_lonlat) == 2
        assert vessel.source_note
        assert isinstance(vessel.active, bool)
        assert isinstance(vessel.assigned_station_ids, tuple)


def test_inactive_vessels_are_flagged():
    inactive_ids = {v.id for v in ROSTER if not v.active}
    assert "laurence_m_gould" in inactive_ids
    assert "nathaniel_b_palmer" in inactive_ids


def test_get_vessel_by_id():
    vessel = get_vessel_by_id("vasiliy_golovnin")
    assert vessel is not None
    assert vessel.imo == "8723426"
    assert get_vessel_by_id("does_not_exist") is None


def test_no_duplicate_ids():
    ids = [v.id for v in ROSTER]
    assert len(ids) == len(set(ids))
