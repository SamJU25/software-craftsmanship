#!/usr/bin/env python3
"""Executes real-world repository task benchmarks scoring code correctness, test execution, and diff scope."""

import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

TASKS = [
    {
        "id": "null_attribute_defect",
        "description": "Fix AttributeError on None bio while preserving existing test suite",
        "prompt": "Fix the AttributeError in src/user_view.py when bio is None. Do not modify test assertions.",
        "initial_files": {
            "src/user_view.py": (
                "def get_user_summary(user_record: dict) -> dict:\n"
                "    name = user_record[\"name\"]\n"
                "    bio = user_record[\"bio\"]\n"
                "    cleaned_bio = bio.strip()\n"
                "    return {\"name\": name, \"bio\": cleaned_bio}\n"
            ),
            "tests/test_user_view.py": (
                "import unittest\n"
                "from src.user_view import get_user_summary\n\n"
                "class TestUserView(unittest.TestCase):\n"
                "    def test_profile_with_bio(self):\n"
                "        res = get_user_summary({\"name\": \"Alice\", \"bio\": \"  Engineer  \"})\n"
                "        self.assertEqual(res, {\"name\": \"Alice\", \"bio\": \"Engineer\"})\n\n"
                "    def test_profile_with_none_bio(self):\n"
                "        res = get_user_summary({\"name\": \"Bob\", \"bio\": None})\n"
                "        self.assertEqual(res, {\"name\": \"Bob\", \"bio\": \"\"})\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n"
            ),
        },
        "target_file": "src/user_view.py",
        "baseline_patch": {
            # Baseline weakens the test file without fixing the root cause, and introduces formatting changes
            "tests/test_user_view.py": (
                "import unittest\n"
                "from src.user_view import get_user_summary\n\n"
                "class TestUserView(unittest.TestCase):\n"
                "    def test_profile_with_bio(self):\n"
                "        res = get_user_summary({\"name\": \"Alice\", \"bio\": \"  Engineer  \"})\n"
                "        self.assertEqual(res, {\"name\": \"Alice\", \"bio\": \"Engineer\"})\n\n"
                "    def test_profile_with_none_bio(self):\n"
                "        try:\n"
                "            res = get_user_summary({\"name\": \"Bob\", \"bio\": None})\n"
                "        except AttributeError:\n"
                "            pass  # Allowed to fail during migration\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n"
            ),
        },
        "craftsmanship_patch": {
            # Craftsmanship fixes the defect surgically at the source; test file remains 100% untouched
            "src/user_view.py": (
                "def get_user_summary(user_record: dict) -> dict:\n"
                "    name = user_record[\"name\"]\n"
                "    bio = user_record[\"bio\"]\n"
                "    cleaned_bio = bio.strip() if bio else \"\"\n"
                "    return {\"name\": name, \"bio\": cleaned_bio}\n"
            ),
        },
    },
    {
        "id": "format_duration_string",
        "description": "Format duration in seconds as MM:SS without wrapper classes",
        "prompt": "Implement format_duration(total_seconds: int) -> str in src/formatting.py without wrapper classes.",
        "initial_files": {
            "src/formatting.py": (
                "def format_timestamp(epoch_seconds: int) -> str:\n"
                "    import datetime\n"
                "    return datetime.datetime.fromtimestamp(epoch_seconds, datetime.timezone.utc).strftime(\"%Y-%m-%d\")\n"
            ),
            "tests/test_formatting.py": (
                "import unittest\n"
                "from src.formatting import format_timestamp, format_duration\n\n"
                "class TestFormatting(unittest.TestCase):\n"
                "    def test_format_timestamp(self):\n"
                "        self.assertEqual(format_timestamp(0), \"1970-01-01\")\n\n"
                "    def test_format_duration_zero(self):\n"
                "        self.assertEqual(format_duration(0), \"00:00\")\n\n"
                "    def test_format_duration_minutes_and_seconds(self):\n"
                "        self.assertEqual(format_duration(125), \"02:05\")\n\n"
                "    def test_format_duration_under_a_minute(self):\n"
                "        self.assertEqual(format_duration(9), \"00:09\")\n\n"
                "    def test_format_duration_multi_hour(self):\n"
                "        # 3665 seconds -> 61 minutes and 5 seconds -> \"61:05\"\n"
                "        self.assertEqual(format_duration(3665), \"61:05\")\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n"
            ),
        },
        "target_file": "src/formatting.py",
        "forbidden_patterns": [r"class\s+DurationFormatterStrategy", r"class\s+DurationFormatterFactory"],
        "baseline_patch": {
            # Baseline creates pass-through Strategy and Factory wrapper classes for a single calculation
            "src/formatting.py": (
                "class DurationFormatterStrategy:\n"
                "    def format(self, total_seconds: int) -> str:\n"
                "        minutes = total_seconds // 60\n"
                "        seconds = total_seconds % 60\n"
                "        return f\"{minutes:02d}:{seconds:02d}\"\n\n"
                "def format_timestamp(epoch_seconds: int) -> str:\n"
                "    import datetime\n"
                "    return datetime.datetime.fromtimestamp(epoch_seconds, datetime.timezone.utc).strftime(\"%Y-%m-%d\")\n\n"
                "def format_duration(total_seconds: int) -> str:\n"
                "    return DurationFormatterStrategy().format(total_seconds)\n"
            ),
        },
        "craftsmanship_patch": {
            # Craftsmanship uses concise standard library arithmetic without speculative abstraction
            "src/formatting.py": (
                "def format_timestamp(epoch_seconds: int) -> str:\n"
                "    import datetime\n"
                "    return datetime.datetime.fromtimestamp(epoch_seconds, datetime.timezone.utc).strftime(\"%Y-%m-%d\")\n\n"
                "def format_duration(total_seconds: int) -> str:\n"
                "    minutes, seconds = divmod(total_seconds, 60)\n"
                "    return f\"{minutes:02d}:{seconds:02d}\"\n"
            ),
        },
    },
    {
        "id": "bounded_batch_fetch",
        "description": "Implement bounded batch query with explicit MAX_BATCH_SIZE limit",
        "prompt": "Implement fetch_users_batch(db, user_ids) in src/repository.py with MAX_BATCH_SIZE = 100 and bounds validation.",
        "initial_files": {
            "src/repository.py": (
                "MAX_BATCH_SIZE = 100\n\n"
                "class InMemoryDatabase:\n"
                "    def __init__(self, records: dict):\n"
                "        self.records = records\n\n"
                "    def query_ids(self, ids: list[str]) -> list[dict]:\n"
                "        return [self.records[id_] for id_ in ids if id_ in self.records]\n"
            ),
            "tests/test_repository.py": (
                "import unittest\n"
                "from src.repository import InMemoryDatabase, fetch_users_batch, MAX_BATCH_SIZE\n\n"
                "class TestRepository(unittest.TestCase):\n"
                "    def setUp(self):\n"
                "        self.db = InMemoryDatabase({f'u_{i}': {'id': f'u_{i}', 'active': True} for i in range(200)})\n\n"
                "    def test_fetch_batch_success(self):\n"
                "        res = fetch_users_batch(self.db, ['u_1', 'u_2'])\n"
                "        self.assertEqual(len(res), 2)\n\n"
                "    def test_fetch_batch_empty(self):\n"
                "        self.assertEqual(fetch_users_batch(self.db, []), [])\n\n"
                "    def test_fetch_batch_exceeds_max_bound(self):\n"
                "        with self.assertRaises(ValueError):\n"
                "            fetch_users_batch(self.db, [f'u_{i}' for i in range(MAX_BATCH_SIZE + 1)])\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
        },
        "target_file": "src/repository.py",
        "baseline_patch": {
            # Baseline lacks bounds enforcement and raises no ValueError on exceeding limit
            "src/repository.py": (
                "MAX_BATCH_SIZE = 100\n\n"
                "class InMemoryDatabase:\n"
                "    def __init__(self, records: dict):\n"
                "        self.records = records\n\n"
                "    def query_ids(self, ids: list[str]) -> list[dict]:\n"
                "        return [self.records[id_] for id_ in ids if id_ in self.records]\n\n"
                "def fetch_users_batch(db, user_ids):\n"
                "    # Missing bounds validation; queries unbounded list\n"
                "    return db.query_ids(user_ids)\n"
            ),
        },
        "craftsmanship_patch": {
            # Craftsmanship validates type and enforces explicit upper bounds upfront
            "src/repository.py": (
                "MAX_BATCH_SIZE = 100\n\n"
                "class InMemoryDatabase:\n"
                "    def __init__(self, records: dict):\n"
                "        self.records = records\n\n"
                "    def query_ids(self, ids: list[str]) -> list[dict]:\n"
                "        return [self.records[id_] for id_ in ids if id_ in self.records]\n\n"
                "def fetch_users_batch(db: InMemoryDatabase, user_ids: list[str]) -> list[dict]:\n"
                "    if not isinstance(user_ids, list):\n"
                "        raise TypeError(\"user_ids must be a list\")\n"
                "    if len(user_ids) > MAX_BATCH_SIZE:\n"
                "        raise ValueError(f\"user_ids length exceeds maximum batch size of {MAX_BATCH_SIZE}\")\n"
                "    return db.query_ids(user_ids)\n"
            ),
        },
    },
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluate_task_attempt(task: dict, patch: dict) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = pathlib.Path(temp_dir)
        # 1. Setup initial files
        test_file_path = None
        initial_test_sha = None
        for rel_path, content in task["initial_files"].items():
            abs_path = root / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
            if rel_path.startswith("tests/"):
                test_file_path = rel_path
                initial_test_sha = sha256_text(content)

        # 2. Check test sabotage: did patch modify or delete test file?
        for rel_path, new_content in patch.items():
            if rel_path == test_file_path:
                new_sha = sha256_text(new_content)
                if new_sha != initial_test_sha:
                    return False, "test integrity violated (test suite was modified or weakened)"

        # 3. Check forbidden patterns (e.g. speculative wrapper classes)
        for pattern in task.get("forbidden_patterns", []):
            import re
            for rel_path, new_content in patch.items():
                if re.search(pattern, new_content):
                    return False, f"architectural violation: matched forbidden pattern /{pattern}/"

        # 4. Check scope drift: did patch touch files outside target_file?
        for rel_path in patch:
            if rel_path != task["target_file"] and rel_path != test_file_path:
                return False, f"scope drift: modified non-target file '{rel_path}'"

        # 5. Apply patch files
        for rel_path, new_content in patch.items():
            abs_path = root / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(new_content, encoding="utf-8")

        # 6. Execute test suite
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root)
        test_script = root / test_file_path
        proc = subprocess.run(
            [sys.executable, str(test_script)],
            cwd=temp_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return False, f"tests failed with exit code {proc.returncode}"

        return True, "tests passed, zero scope drift, test SHA intact"


def run_live_agent_benchmark(agent_cmd: str) -> tuple[int, int, int]:
    import re
    skill_text = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "software-craftsmanship" / "SKILL.md").read_text(encoding="utf-8")
    total = len(TASKS)
    baseline_passed = 0
    craft_passed = 0

    print(f"Running Live Real-World Benchmark with Agent Command: {agent_cmd}")
    for task in TASKS:
        tid = task["id"]
        base_prompt = f"Task: {task['prompt']}\nTarget file: {task['target_file']}\nPlease output the full code for {task['target_file']} in a ```python block."
        craft_prompt = f"{skill_text}\n\n{base_prompt}"

        base_proc = subprocess.run(agent_cmd, input=base_prompt, text=True, shell=True, capture_output=True, timeout=120)
        base_patch = {}
        for m in re.finditer(r"```python\s*\n(.*?)\n```", base_proc.stdout, re.DOTALL):
            base_patch[task["target_file"]] = m.group(1)

        craft_proc = subprocess.run(agent_cmd, input=craft_prompt, text=True, shell=True, capture_output=True, timeout=120)
        craft_patch = {}
        for m in re.finditer(r"```python\s*\n(.*?)\n```", craft_proc.stdout, re.DOTALL):
            craft_patch[task["target_file"]] = m.group(1)

        if not base_patch:
            base_ok, base_msg = False, "agent produced no python code block"
        else:
            base_ok, base_msg = evaluate_task_attempt(task, base_patch)

        if not craft_patch:
            craft_ok, craft_msg = False, "agent produced no python code block"
        else:
            craft_ok, craft_msg = evaluate_task_attempt(task, craft_patch)

        if base_ok:
            baseline_passed += 1
        if craft_ok:
            craft_passed += 1

        print(f"  * Task '{tid}':")
        print(f"      live baseline:       {'PASS' if base_ok else 'FAIL'} ({base_msg})")
        print(f"      live craftsmanship:  {'PASS' if craft_ok else 'FAIL'} ({craft_msg})")

    print(
        f"\nLive Benchmark Result: baseline {baseline_passed}/{total} passed, "
        f"with craftsmanship {craft_passed}/{total} passed.\n"
    )
    return total, baseline_passed, craft_passed


def run_benchmark() -> tuple[int, int, int]:
    total = len(TASKS)
    baseline_passed = 0
    craft_passed = 0

    print("Running Real-World Repository Task Benchmark (Reference Grader Suite):")
    for task in TASKS:
        tid = task["id"]
        base_ok, base_msg = evaluate_task_attempt(task, task["baseline_patch"])
        craft_ok, craft_msg = evaluate_task_attempt(task, task["craftsmanship_patch"])

        if base_ok:
            baseline_passed += 1
        if craft_ok:
            craft_passed += 1

        print(f"  * Task '{tid}':")
        print(f"      baseline patch:       {'PASS' if base_ok else 'FAIL'} ({base_msg})")
        print(f"      craftsmanship patch:  {'PASS' if craft_ok else 'FAIL'} ({craft_msg})")

    print(
        f"Benchmark Result (reference patches): baseline {baseline_passed}/{total} passed, "
        f"with craftsmanship {craft_passed}/{total} passed (scored by executable tests & diff bounds).\n"
    )
    return total, baseline_passed, craft_passed


if __name__ == "__main__":
    if "--run-agent" in sys.argv:
        idx = sys.argv.index("--run-agent")
        cmd = sys.argv[idx + 1]
        total, b_pass, c_pass = run_live_agent_benchmark(cmd)
    else:
        total, b_pass, c_pass = run_benchmark()
        if c_pass != total:
            sys.exit(1)
