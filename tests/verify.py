#!/usr/bin/env python3
"""Synchronizes rule templates from SKILL.md, checks prose/schema rules, and grades behavioral evals."""

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "software-craftsmanship" / "SKILL.md"
AGENTS_PATH = ROOT / "templates" / "AGENTS.md"
CURSOR_PATH = ROOT / "templates" / "software-craftsmanship.mdc"
README_PATH = ROOT / "README.md"
EVALS_PATH = ROOT / "tests" / "evals.json"
EVAL_RESULTS_PATH = ROOT / "tests" / "eval_results.json"

CURSOR_FRONTMATTER = """---
description: Engineering standard and natural writing guidelines for software and documentation.
globs: "**/*"
alwaysApply: true
---

"""

JSON_MANIFESTS = [
    ROOT / "plugin.json",
    ROOT / ".antigravity-plugin" / "plugin.json",
    ROOT / ".claude-plugin" / "plugin.json",
    ROOT / ".claude-plugin" / "marketplace.json",
    ROOT / ".codex-plugin" / "plugin.json",
    ROOT / ".cursor-plugin" / "plugin.json",
    ROOT / "gemini-extension.json",
]

MAX_SKILL_CHARS = 12000


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("Missing opening YAML frontmatter delimiter")
    parts = text.split("\n---\n\n", 1)
    if len(parts) != 2:
        raise ValueError("Missing closing YAML frontmatter delimiter")
    return parts[0][4:], parts[1]


def sync_templates() -> None:
    skill_content = SKILL_PATH.read_text(encoding="utf-8")
    _, body = split_frontmatter(skill_content)
    AGENTS_PATH.write_text(body, encoding="utf-8", newline="\n")
    CURSOR_PATH.write_text(CURSOR_FRONTMATTER + body, encoding="utf-8", newline="\n")
    global_skill = pathlib.Path.home() / ".gemini" / "config" / "skills" / "software-craftsmanship" / "SKILL.md"
    if global_skill.parent.exists():
        global_skill.write_text(skill_content, encoding="utf-8", newline="\n")


def grade_output(case: dict, output: str) -> list[str]:
    failures = []
    for pattern in case.get("must_match", []):
        if not re.search(pattern, output, re.IGNORECASE | re.MULTILINE):
            failures.append(f"missing required pattern /{pattern}/")
    for pattern in case.get("must_not_match", []):
        if re.search(pattern, output, re.IGNORECASE | re.MULTILINE):
            failures.append(f"matched forbidden pattern /{pattern}/")
    return failures


def run_live_agent(agent_cmd: str, evals: list[dict], skill_text: str) -> None:
    results = []
    for case in evals:
        base_prompt = f"Context: {case['context']}\nMode: {case['mode']}\nTask: {case['prompt']}"
        craft_prompt = f"{skill_text}\n\n{base_prompt}"
        base_proc = subprocess.run(
            agent_cmd, input=base_prompt, text=True, shell=True, capture_output=True, timeout=120
        )
        craft_proc = subprocess.run(
            agent_cmd, input=craft_prompt, text=True, shell=True, capture_output=True, timeout=120
        )
        results.append(
            {
                "id": case["id"],
                "baseline_output": base_proc.stdout.strip(),
                "skill_output": craft_proc.stdout.strip(),
                "craftsmanship_output": craft_proc.stdout.strip(),
            }
        )
    EVAL_RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n")


def verify_code_syntax(results: list[dict]) -> int:
    validated = 0
    for r in results:
        text = r.get("skill_output") or r.get("craftsmanship_output", "")
        # Validate Python syntax with AST
        for m in re.finditer(r"```python\s*\n(.*?)\n```", text, re.DOTALL):
            import ast
            ast.parse(m.group(1))
            validated += 1
        # Validate unified diff headers
        for m in re.finditer(r"```diff\s*\n(.*?)\n```", text, re.DOTALL):
            diff = m.group(1)
            if not ("---" in diff and "+++" in diff and "@@" in diff):
                raise AssertionError(f"Malformed unified diff block in {r['id']}")
            validated += 1
    return validated


def verify() -> None:
    if (ROOT / "SKILL.md").exists():
        raise AssertionError("Root SKILL.md must not exist; it causes npx skills to copy the entire repository.")

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(skill_text)

    if "name: software-craftsmanship" not in frontmatter:
        raise AssertionError("SKILL.md frontmatter missing name: software-craftsmanship")

    desc_lines = [line.strip() for line in frontmatter.splitlines() if line.startswith("  ")]
    description = " ".join(desc_lines)
    if not (50 <= len(description) <= 300):
        raise AssertionError(f"Description length {len(description)} outside [50, 300] bounds")

    if len(skill_text) > MAX_SKILL_CHARS:
        raise AssertionError(f"SKILL.md length {len(skill_text)} exceeds budget {MAX_SKILL_CHARS}")

    agents_body = AGENTS_PATH.read_text(encoding="utf-8")
    _, cursor_body = split_frontmatter(CURSOR_PATH.read_text(encoding="utf-8"))
    if body != agents_body:
        raise AssertionError("templates/AGENTS.md is out of sync with SKILL.md (run: python tests/verify.py --sync)")
    if body != cursor_body:
        raise AssertionError("templates/software-craftsmanship.mdc is out of sync with SKILL.md (run: python tests/verify.py --sync)")

    for path in [SKILL_PATH, AGENTS_PATH, CURSOR_PATH, README_PATH]:
        content = path.read_text(encoding="utf-8")
        if "\u2014" in content:
            raise AssertionError(f"Em-dash found in {path.relative_to(ROOT)}")

    for path in [SKILL_PATH, AGENTS_PATH, CURSOR_PATH]:
        content = path.read_text(encoding="utf-8")
        for phrase in ("rather than", "instead of"):
            if re.search(rf"\b{phrase}\b", content, re.IGNORECASE):
                raise AssertionError(f"Contrast phrase '{phrase}' found in {path.relative_to(ROOT)}")

    slop_patterns = [
        (
            r"\b(certainly|sure thing|here is an overview|delighted to|as an ai language model|as requested|absolutely|i\'d be happy to|glad to help|here\'s what you need to know)\b",
            "sycophantic opener",
        ),
        (
            r"\b(delve|delving|delved|tapestry|beacon|foster(?:ing)?|revolutioniz\w+|supercharge|game-changer|pivotal|multifaceted|plethora|paradigm shift|synergy|linchpin|testament|bespoke|spearhead|unleash(?:ing)?)\b",
            "cliche vocabulary",
        ),
        (
            r"\bin today\'s (?:fast-paced|digital|modern|interconnected|dynamic|ever-changing|rapidly evolving)\b",
            "macro throat-clearing",
        ),
        (
            r"\b(?:in the realm of|in the world of|when it comes to|at the end of the day)\b",
            "throat-clearing filler",
        ),
        (
            r"\b(?:it is (?:worth noting|important to (?:note|remember)|crucial to understand))\b",
            "metadiscourse filler",
        ),
        (
            r"\b(?:harness(?:ing)?\s+(?:the|its|our|ai)|take\s+(?:\w+\s+)?to the next level|dive deep into|unlock(?:ing)? the potential)\b",
            "cliche verb phrase",
        ),
        (
            r"\bnot (?:just|only|merely|simply)\b[^\n.!?]{1,80}\b(?:it is|is also|but|rather|instead)\b",
            "contrast slogan",
        ),
        (
            r"\b(?:it is|it\'s) not about\b[^\n.!?]{1,60}\b(?:it\'s about|it is about)\b",
            "contrast slogan identity",
        ),
        (
            r"\bnot a\b[^\n.!?]{1,40}\b,\s*but (?:a|an|rather)\b",
            "binary contrast framing",
        ),
        (
            r"\b(blazing-fast|seamlessly|effortlessly|state-of-the-art|cutting-edge|groundbreaking|world-class|robust and scalable|next-generation|game-changing)\b",
            "promotional buzzword",
        ),
        (
            r",\s*(?:ensuring|fostering|enabling|facilitating)\s+(?:seamless|optimal|effortless|maximum|blazing)",
            "participial filler tail",
        ),
    ]
    for path in [SKILL_PATH, AGENTS_PATH, CURSOR_PATH]:
        content = path.read_text(encoding="utf-8")
        for pattern, label in slop_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                raise AssertionError(f"AI slop pattern '{label}' ({pattern}) found in {path.relative_to(ROOT)}")

    for manifest in JSON_MANIFESTS:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if "name" not in data:
            raise AssertionError(f"Missing 'name' in {manifest.relative_to(ROOT)}")

    evals = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
    if not isinstance(evals, list) or len(evals) < 5:
        raise AssertionError("tests/evals.json must contain at least 5 evaluation scenarios")
    required_keys = {"id", "category", "mode", "prompt", "context", "must_include", "must_avoid", "must_match", "must_not_match"}
    for case in evals:
        missing = required_keys - set(case.keys())
        if missing:
            raise AssertionError(f"Eval case {case.get('id')} missing keys: {missing}")

    if not EVAL_RESULTS_PATH.exists():
        raise AssertionError("Missing tests/eval_results.json recorded behavioral evaluation outputs")

    results_by_id = {item["id"]: item for item in json.loads(EVAL_RESULTS_PATH.read_text(encoding="utf-8"))}
    baseline_passed = 0
    craft_passed = 0
    total_assertions = 0

    for case in evals:
        cid = case["id"]
        if cid not in results_by_id:
            raise AssertionError(f"Missing eval result for case '{cid}' in tests/eval_results.json")
        res = results_by_id[cid]
        skill_output = res.get("skill_output") or res.get("craftsmanship_output")
        if not skill_output:
            raise AssertionError(f"Missing skill_output for eval case '{cid}' in tests/eval_results.json")
        base_failures = grade_output(case, res.get("baseline_output", ""))
        craft_failures = grade_output(case, skill_output)
        for pattern, label in slop_patterns:
            if re.search(pattern, skill_output, re.IGNORECASE):
                craft_failures.append(f"matched slop pattern '{label}' ({pattern})")
        for phrase in ("rather than", "instead of"):
            if re.search(rf"\b{phrase}\b", skill_output, re.IGNORECASE):
                craft_failures.append(f"matched contrast phrase '{phrase}'")
        if "\u2014" in skill_output:
            craft_failures.append("matched em-dash")
        total_assertions += len(case["must_match"]) + len(case["must_not_match"]) + len(slop_patterns) + 3
        if not base_failures:
            baseline_passed += 1
        if craft_failures:
            raise AssertionError(f"Skill output failed eval '{cid}': {craft_failures}")
        craft_passed += 1

    syntax_blocks = verify_code_syntax(json.loads(EVAL_RESULTS_PATH.read_text(encoding="utf-8")))

    words = len(skill_text.split())
    print(f"OK: templates synced, {len(JSON_MANIFESTS)} manifests valid, zero contrast tics or em-dashes.")
    print(
        f"Behavioral evals graded ({total_assertions} assertions, {syntax_blocks} verified code blocks across {len(evals)} cases): "
        f"baseline {baseline_passed}/{len(evals)} passed, with skill_output {craft_passed}/{len(evals)} passed."
    )
    print(f"SKILL.md size: {words} words, {len(skill_text)} chars (~{int(words * 1.3)} tokens).\n")

    sys.path.insert(0, str(ROOT / "tests"))
    import benchmark
    bench_total, bench_base, bench_craft = benchmark.run_benchmark()
    if bench_craft != bench_total:
        raise AssertionError(f"Repository benchmark failed: only {bench_craft}/{bench_total} passed")


if __name__ == "__main__":
    if "--sync" in sys.argv:
        sync_templates()
    if "--run-agent" in sys.argv:
        idx = sys.argv.index("--run-agent")
        cmd = sys.argv[idx + 1]
        run_live_agent(
            cmd,
            json.loads(EVALS_PATH.read_text(encoding="utf-8")),
            SKILL_PATH.read_text(encoding="utf-8"),
        )
    verify()
