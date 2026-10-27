import pytest

pytestmark = pytest.mark.unit


def test_job_queue_survives_a_failing_callback(tmp_path):
    import time
    from reeluniq.jobs import Job, JobQueue

    seen = []
    q = JobQueue(on_done=lambda j: (seen.append(j.id), 1 / 0))
    for i in range(2):
        q.submit(Job(id=str(i), source=tmp_path / "missing.mp4", out_dir=tmp_path / str(i), count=1, mode="light"))
    for _ in range(100):
        if len(seen) == 2:
            break
        time.sleep(0.1)
    assert seen == ["0", "1"] and all(j.state == "failed" for j in q.jobs.values())
