"""A new staff-role remark must not silently expand a sealed allowlist."""
from test_nn_timing_bounded_batches import batch


def test_same_warning_with_new_staff_role_is_still_unknown():
    known="38'\u8b66\u544a(C3)SyntheticClubStaff(\u76e3\u7763)"
    unseen="38'\u8b66\u544a(C3)SyntheticClubStaff(\u901a\u8a33)"
    assert batch.remarks_classification({'status':'PASS','remarks':[known],'timing_notes':[]})=='KNOWN_NON_TIMING_NOTE'
    assert batch.remarks_classification({'status':'PASS','remarks':[unseen],'timing_notes':[]})=='UNKNOWN_FORMAT'


def test_mixed_known_and_unseen_remarks_cannot_pass_by_partial_matching():
    notes=["84'\u8b66\u544a(C3)SyntheticCoach(\u76e3\u7763)","38'\u8b66\u544a(C3)SyntheticStaff(\u901a\u8a33)"]
    assert batch.remarks_classification({'status':'PASS','remarks':notes,'timing_notes':[]})=='UNKNOWN_FORMAT'
