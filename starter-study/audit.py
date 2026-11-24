"""Recreate tasks.json from local checkouts of the official starter and PLE kit."""
import argparse
import json
from pathlib import Path

import yaml


def summarize(starter, kit):
    artifacts = starter / "artifacts"
    tasks = json.loads((artifacts / "manifest.json").read_text())["tasks"]
    definitions = yaml.safe_load((kit / "eval/dev_set.yaml").read_text())
    domains = {row["id"]: row["domain"].split()[0] for row in definitions["tasks"]}
    if tasks.keys() != domains.keys():
        raise ValueError("The manifest and dev-set task IDs differ")
    rows = []
    for task_id, record in sorted(tasks.items()):
        trace = json.loads((artifacts / task_id / "trajectory.json").read_text())
        turns = [step for step in trace["steps"] if step["source"] == "agent"]
        rows.append({
            "id": task_id,
            "steps": len(turns),
            "calls": sum(len(turn.get("tool_calls") or []) for turn in turns),
            "model": trace["agent"]["model_name"],
            "reward": record["reward"],
            "files": len(record["files"]),
            "discipline": domains[task_id],
        })
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("starter", type=Path)
    parser.add_argument("kit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.starter, args.kit), indent=2) + "\n")
