#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Teacher:
    name: str
    subject: str
    weekly_hours: int
    grades: Tuple[int, ...]
    unavailable: Tuple[str, ...]


@dataclass
class Problem:
    days: List[str]
    periods_per_day: int
    grade_classes: Dict[int, int]
    grade_subject_hours: Dict[int, Dict[str, int]]
    teachers: List[Teacher]
    class_unavailable: Dict[str, List[str]]
    max_same_subject_per_day: int


class ScheduleSolver:
    def __init__(self, problem: Problem):
        self.problem = problem
        self.slots = [f"{day}-{p}" for day in problem.days for p in range(1, problem.periods_per_day + 1)]
        self.class_ids = [
            f"{grade}-{class_no}"
            for grade, class_count in sorted(problem.grade_classes.items())
            for class_no in range(1, class_count + 1)
        ]
        self.class_grade = {class_id: int(class_id.split("-")[0]) for class_id in self.class_ids}

        self.teacher_by_name = {t.name: t for t in problem.teachers}
        self.teachers_by_subject_grade: Dict[Tuple[str, int], List[str]] = {}
        for t in problem.teachers:
            for g in t.grades:
                self.teachers_by_subject_grade.setdefault((t.subject, g), []).append(t.name)

        self.remaining_requirements = self._build_initial_requirements()
        self.class_schedule = {c: {s: None for s in self.slots} for c in self.class_ids}
        self.teacher_schedule = {t.name: {s: None for s in self.slots} for t in problem.teachers}
        self.teacher_load = {t.name: 0 for t in problem.teachers}
        self.class_subject_day_count = {
            c: {subject: {day: 0 for day in problem.days} for subject in self._subjects_for_class(c)}
            for c in self.class_ids
        }
        self.solutions: List[Dict[str, Dict[str, str]]] = []

    def _subjects_for_class(self, class_id: str) -> List[str]:
        grade = self.class_grade[class_id]
        return list(self.problem.grade_subject_hours.get(grade, {}).keys())

    def _build_initial_requirements(self) -> Dict[Tuple[str, str], int]:
        req: Dict[Tuple[str, str], int] = {}
        for class_id in self.class_ids:
            grade = self.class_grade[class_id]
            for subject, hours in self.problem.grade_subject_hours.get(grade, {}).items():
                req[(class_id, subject)] = hours
        return req

    def solve(self, max_solutions: int = 3) -> List[Dict[str, Dict[str, str]]]:
        self._backtrack(max_solutions=max_solutions)
        return self.solutions

    def _backtrack(self, max_solutions: int):
        if len(self.solutions) >= max_solutions:
            return

        target = self._select_next_requirement()
        if target is None:
            solved = {
                class_id: {
                    slot: (assignment if assignment is not None else "-")
                    for slot, assignment in slots.items()
                }
                for class_id, slots in self.class_schedule.items()
            }
            self.solutions.append(copy.deepcopy(solved))
            return

        class_id, subject = target
        grade = self.class_grade[class_id]
        candidate_teachers = self.teachers_by_subject_grade.get((subject, grade), [])
        if not candidate_teachers:
            return

        for slot in self.slots:
            if not self._can_place_class_slot(class_id, subject, slot):
                continue

            for teacher_name in candidate_teachers:
                if not self._can_assign_teacher(teacher_name, slot):
                    continue

                self._place(class_id, subject, teacher_name, slot)
                self._backtrack(max_solutions=max_solutions)
                self._unplace(class_id, subject, teacher_name, slot)

                if len(self.solutions) >= max_solutions:
                    return

    def _select_next_requirement(self) -> Optional[Tuple[str, str]]:
        remaining = [(key, value) for key, value in self.remaining_requirements.items() if value > 0]
        if not remaining:
            return None

        scored: List[Tuple[int, Tuple[str, str]]] = []
        for (class_id, subject), _ in remaining:
            grade = self.class_grade[class_id]
            teachers = self.teachers_by_subject_grade.get((subject, grade), [])
            feasible_slots = 0
            for slot in self.slots:
                if self._can_place_class_slot(class_id, subject, slot):
                    if any(self._can_assign_teacher(t, slot) for t in teachers):
                        feasible_slots += 1
            scored.append((feasible_slots, (class_id, subject)))

        scored.sort(key=lambda x: x[0])
        return scored[0][1]

    def _can_place_class_slot(self, class_id: str, subject: str, slot: str) -> bool:
        if self.class_schedule[class_id][slot] is not None:
            return False
        if slot in self.problem.class_unavailable.get(class_id, []):
            return False

        day = slot.split("-")[0]
        if self.class_subject_day_count[class_id][subject][day] >= self.problem.max_same_subject_per_day:
            return False
        return True

    def _can_assign_teacher(self, teacher_name: str, slot: str) -> bool:
        teacher = self.teacher_by_name[teacher_name]
        if slot in teacher.unavailable:
            return False
        if self.teacher_schedule[teacher_name][slot] is not None:
            return False
        if self.teacher_load[teacher_name] >= teacher.weekly_hours:
            return False
        return True

    def _place(self, class_id: str, subject: str, teacher_name: str, slot: str):
        label = f"{subject}({teacher_name})"
        self.class_schedule[class_id][slot] = label
        self.teacher_schedule[teacher_name][slot] = class_id
        self.teacher_load[teacher_name] += 1
        self.remaining_requirements[(class_id, subject)] -= 1
        day = slot.split("-")[0]
        self.class_subject_day_count[class_id][subject][day] += 1

    def _unplace(self, class_id: str, subject: str, teacher_name: str, slot: str):
        self.class_schedule[class_id][slot] = None
        self.teacher_schedule[teacher_name][slot] = None
        self.teacher_load[teacher_name] -= 1
        self.remaining_requirements[(class_id, subject)] += 1
        day = slot.split("-")[0]
        self.class_subject_day_count[class_id][subject][day] -= 1


def load_problem(path: Path) -> Problem:
    raw = json.loads(path.read_text(encoding="utf-8"))
    teachers = [
        Teacher(
            name=t["name"],
            subject=t["subject"],
            weekly_hours=t["weekly_hours"],
            grades=tuple(t["grades"]),
            unavailable=tuple(raw.get("teacher_unavailable", {}).get(t["name"], [])),
        )
        for t in raw["teachers"]
    ]
    return Problem(
        days=raw["days"],
        periods_per_day=raw["periods_per_day"],
        grade_classes={int(k): v for k, v in raw["grade_classes"].items()},
        grade_subject_hours={int(k): v for k, v in raw["grade_subject_hours"].items()},
        teachers=teachers,
        class_unavailable=raw.get("class_unavailable", {}),
        max_same_subject_per_day=raw.get("max_same_subject_per_day", 1),
    )


def print_solution(solution: Dict[str, Dict[str, str]], days: List[str], periods_per_day: int):
    slots = [f"{day}-{p}" for day in days for p in range(1, periods_per_day + 1)]
    for class_id in sorted(solution.keys(), key=lambda x: tuple(map(int, x.split("-")))):
        print(f"\n=== 학급 {class_id} ===")
        for slot in slots:
            print(f"{slot:>8}: {solution[class_id][slot]}")


def main():
    parser = argparse.ArgumentParser(description="초등 전담교사 시간표 자동 생성기")
    parser.add_argument("input", type=Path, help="입력 JSON 파일 경로")
    parser.add_argument("--max-solutions", type=int, default=3, help="생성할 최대 경우의 수")
    parser.add_argument("--output", type=Path, default=Path("solutions.json"), help="출력 JSON 경로")
    args = parser.parse_args()

    problem = load_problem(args.input)
    solver = ScheduleSolver(problem)
    solutions = solver.solve(max_solutions=args.max_solutions)

    if not solutions:
        print("가능한 시간표를 찾지 못했습니다. 제약조건을 완화해 보세요.")
        return

    for idx, sol in enumerate(solutions, start=1):
        print(f"\n############################")
        print(f"가능한 시간표 #{idx}")
        print_solution(sol, problem.days, problem.periods_per_day)

    args.output.write_text(json.dumps(solutions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(solutions)}개 시간표를 {args.output}에 저장했습니다.")


if __name__ == "__main__":
    main()
