import click

from kagan.cli._bootstrap import make_client, run_async


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells))

    lines = [render_row(headers), render_row(["-" * width for width in widths])]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines)


async def _collect_rows(client) -> list[list[str]]:
    from kagan.core import TaskStatus

    projects = await client.projects.list()
    rows: list[list[str]] = []
    for project in projects:
        repos = await client.projects.repos(project.id)
        repo_paths = ", ".join(repo.path for repo in repos) if repos else "-"
        counts = await client.tasks.counts(project_id=project.id)
        backlog = str(counts.get(TaskStatus.BACKLOG, 0))
        in_progress = str(counts.get(TaskStatus.IN_PROGRESS, 0))
        review = str(counts.get(TaskStatus.REVIEW, 0))
        done = str(counts.get(TaskStatus.DONE, 0))
        rows.append([project.name, repo_paths, backlog, in_progress, review, done])
    return rows


@click.command(name="list")
def list_projects() -> None:
    client = make_client()
    try:
        rows = run_async(_collect_rows(client))
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    headers = ["Project", "Repos", "BACKLOG", "IN_PROGRESS", "REVIEW", "DONE"]
    click.echo(_format_table(headers, rows))
