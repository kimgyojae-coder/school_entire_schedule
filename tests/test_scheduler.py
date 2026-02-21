import json
import subprocess
from pathlib import Path


def test_solver_generates_solution(tmp_path: Path):
    input_data = {
        "days": ["Mon", "Tue"],
        "periods_per_day": 2,
        "grade_classes": {"3": 1},
        "grade_subject_hours": {"3": {"음악": 1, "체육": 1}},
        "teachers": [
            {"name": "김음악", "subject": "음악", "weekly_hours": 2, "grades": [3]},
            {"name": "박체육", "subject": "체육", "weekly_hours": 2, "grades": [3]},
        ],
        "class_unavailable": {},
        "teacher_unavailable": {},
        "max_same_subject_per_day": 1,
    }

    input_path = tmp_path / "input.json"
    out_path = tmp_path / "out.json"
    input_path.write_text(json.dumps(input_data, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        ["python3", "scheduler.py", str(input_path), "--max-solutions", "2", "--output", str(out_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data) >= 1
    flat = data[0]["3-1"]
    lessons = " ".join(flat.values())
    assert "음악(" in lessons
    assert "체육(" in lessons
