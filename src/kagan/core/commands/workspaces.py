from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from kagan.core.policy import command

from ._parsing import ParseError, parse_workspace_repo_inputs
from ._serialization import workspace_to_dict

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


@command("workspaces", "list", description="List workspaces, optionally filtered by task.")
async def list_workspaces(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params.get("task_id")
    workspaces = await ctx.api.list_workspaces(task_id=task_id)
    return {
        "workspaces": [workspace_to_dict(ws) for ws in workspaces],
        "count": len(workspaces),
    }


@command(
    "workspaces",
    "get_workspace_path",
    description="Get the filesystem path for a task's workspace.",
)
async def get_workspace_path(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    path = await ctx.api.get_task_workspace_path(task_id)
    return {"path": str(path) if path else ""}


@command(
    "workspaces",
    "provision_workspace",
    profile="operator",
    mutating=True,
    description="Provision a workspace for a task using selected repositories.",
)
async def provision_workspace(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    repos = parse_workspace_repo_inputs(params.get("repos"))
    if isinstance(repos, ParseError):
        raise ValueError(repos.message)
    workspace_id = await ctx.api.provision_workspace(task_id=task_id, repos=repos)
    return {"workspace_id": workspace_id}


@command(
    "workspaces",
    "get_workspace_diff",
    description="Get the diff for a task's workspace against a base branch.",
)
async def get_workspace_diff(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    base_branch = params["base_branch"]
    diff = await ctx.api.get_workspace_diff(task_id, base_branch=base_branch)
    return {"diff": diff}


@command(
    "workspaces",
    "get_workspace_diff_stats",
    description="Get summarized diff stats for a task workspace.",
)
async def get_workspace_diff_stats(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    base_branch = params["base_branch"]
    stats = await ctx.api.get_workspace_diff_stats(task_id, base_branch=base_branch)
    return {"stats": stats}


@command(
    "workspaces",
    "get_workspace_commit_log",
    description="Get commit log for a task workspace against a base branch.",
)
async def get_workspace_commit_log(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    base_branch = params["base_branch"]
    commits = await ctx.api.get_workspace_commit_log(task_id, base_branch=base_branch)
    return {"commits": commits, "count": len(commits)}


@command(
    "workspaces",
    "get_repo_diff",
    description="Get diff details for one repository in a workspace.",
)
async def get_repo_diff(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    workspace_id = params["workspace_id"]
    repo_id = params["repo_id"]
    diff = await ctx.api.get_repo_diff(workspace_id, repo_id)
    return {"diff": dataclasses.asdict(diff) if dataclasses.is_dataclass(diff) else diff}


@command(
    "workspaces",
    "get_all_diffs",
    description="Retrieve all diffs for a workspace.",
)
async def get_all_diffs(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    workspace_id = params["workspace_id"]
    diffs = await ctx.api.get_all_diffs(workspace_id)
    serialized = [dataclasses.asdict(d) if dataclasses.is_dataclass(d) else d for d in diffs]
    return {"diffs": serialized, "count": len(serialized)}


@command(
    "workspaces",
    "rebase_workspace",
    profile="operator",
    mutating=True,
    description="Rebase a task's workspace onto a base branch.",
)
async def rebase_workspace(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    base_branch = params["base_branch"]
    success, message, conflict_files = await ctx.api.rebase_workspace(task_id, base_branch)
    return {"success": success, "message": message, "conflict_files": conflict_files}


@command(
    "workspaces",
    "abort_workspace_rebase",
    profile="operator",
    mutating=True,
    description="Abort an in-progress rebase for a task's workspace.",
)
async def abort_workspace_rebase(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    await ctx.api.abort_workspace_rebase(task_id)
    return {"success": True}


@command(
    "workspaces",
    "merge_repo",
    profile="operator",
    mutating=True,
    description="Merge a single repo's changes.",
)
async def merge_repo(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    from kagan.core.services.workspaces.service import MergeStrategy

    workspace_id = params["workspace_id"]
    repo_id = params["repo_id"]
    strategy = MergeStrategy(params.get("strategy", "direct"))
    result = await ctx.api.merge_repo(
        workspace_id,
        repo_id,
        strategy=strategy,
        pr_title=params.get("pr_title"),
        pr_body=params.get("pr_body"),
        commit_message=params.get("commit_message"),
    )
    return dataclasses.asdict(result)


@command(
    "workspaces",
    "cleanup_orphan_workspaces",
    profile="maintainer",
    mutating=True,
    description="Clean up workspaces whose tasks no longer exist.",
)
async def cleanup_orphan_workspaces(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    valid_task_ids = set(params.get("valid_task_ids", []))
    cleaned = await ctx.api.cleanup_orphaned_workspaces(valid_task_ids)
    return {"cleaned": cleaned, "count": len(cleaned)}


__all__ = [
    "abort_workspace_rebase",
    "cleanup_orphan_workspaces",
    "get_all_diffs",
    "get_repo_diff",
    "get_workspace_commit_log",
    "get_workspace_diff",
    "get_workspace_diff_stats",
    "get_workspace_path",
    "list_workspaces",
    "merge_repo",
    "provision_workspace",
    "rebase_workspace",
]
