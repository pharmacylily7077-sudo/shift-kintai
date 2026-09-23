#!/usr/bin/env python3
import re
import sys
import json
import subprocess
from pathlib import Path

TODO_FILE = Path("TODO.md")
STATE_FILE = Path(".runner_state.json")

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"current_task": None, "failures": 0}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def find_top_task(content):
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        match = re.match(r"^\s*-\s*\[ \]\s*(.+)$", line)
        if match:
            task_title = match.group(1).strip()
            # 次の行以降で検証コマンドを探す
            cmd = None
            for j in range(idx + 1, min(idx + 5, len(lines))):
                cmd_match = re.search(r"-\s*検証:\s*`([^`]+)`", lines[j])
                if cmd_match:
                    cmd = cmd_match.group(1).strip()
                    break
            return idx, task_title, cmd
    return None, None, None

def mark_task_done(content, task_idx):
    lines = content.splitlines()
    lines[task_idx] = re.sub(r"-\s*\[ \]", "- [x]", lines[task_idx])
    return "\n".join(lines) + "\n"

def main():
    if not TODO_FILE.exists():
        print(f"Error: {TODO_FILE} does not exist", file=sys.stderr)
        sys.exit(1)

    content = TODO_FILE.read_text(encoding="utf-8")
    task_idx, task_title, verify_cmd = find_top_task(content)

    if task_idx is None:
        print("🎉 すべてのタスクが完了しています！ (All tasks completed)")
        sys.exit(0)

    if not verify_cmd:
        print(f"Error: No verification command found for task: {task_title}", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    if state.get("current_task") != task_title:
        state = {"current_task": task_title, "failures": 0}

    print(f"\n=======================================================")
    print(f"▶ 実行対象タスク: {task_title}")
    print(f"▶ 検証コマンド: {verify_cmd}")
    print(f"=======================================================\n")

    res = subprocess.run(verify_cmd, shell=True, text=True, capture_output=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)

    if res.returncode == 0:
        print(f"\n✅ 検証成功: {task_title}")
        new_content = mark_task_done(content, task_idx)
        TODO_FILE.write_text(new_content, encoding="utf-8")
        
        # リセット
        state = {"current_task": None, "failures": 0}
        save_state(state)

        # 自動コミット
        subprocess.run(["git", "add", "."], check=False)
        commit_msg = f"feat/test: {task_title} 完了"
        subprocess.run(["git", "commit", "-m", commit_msg], check=False)
        print(f"📦 Gitコミット完了: {commit_msg}")
        sys.exit(0)
    else:
        state["failures"] = state.get("failures", 0) + 1
        save_state(state)
        print(f"\n❌ 検証失敗 ({state['failures']}回目): Exit Code {res.returncode}", file=sys.stderr)
        if state["failures"] >= 5:
            print("🚨 リミッター発動: 同一タスクで5回失敗したため強制停止します (Exit Code 2)", file=sys.stderr)
            sys.exit(2)
        sys.exit(1)

if __name__ == "__main__":
    main()
