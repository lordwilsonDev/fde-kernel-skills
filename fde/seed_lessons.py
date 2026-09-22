import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kernel as K, simulator as S


def seed(path):
    if os.path.exists(path):
        os.remove(path)
    k = K.Kernel(path)
    # gaps observed in the M003 closed-loop runs (both conditions), closed into regression tests
    k.add_gap(
        "M003",
        "impact_quantification",
        "Neither run requested an impact_estimate; support-contact proxy left as the only impact figure.",
        "L2",
    )
    k.close_gap_to_regression(
        1,
        "test_impact_proxy_not_total",
        "Impact may not be established from proxy counts; request an impact_estimate artifact.",
    )
    k.add_gap(
        "M003",
        "contradiction_resolution",
        "Raw run opened 2 contradictions and resolved none; no discriminating-evidence link.",
        "L5",
    )
    k.close_gap_to_regression(
        2,
        "test_contradiction_needs_discriminating_evidence_after_open",
        "Contradictions resolve only with discriminating evidence ingested after opening.",
    )
    for l in S.LESSONS:
        k.promote_lesson(
            l["lesson_id"], "M003", l["domain"], l["lesson"], l["transferable"], l["test"]
        )
    k.c.commit()
    return path


if __name__ == "__main__":
    print(seed(sys.argv[1]))
