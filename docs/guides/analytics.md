---
title: Analytics & Metrics
description: Track agent performance, session activity, and export analytics data across all Kagan surfaces.
---

# Analytics & Metrics

Kagan tracks performance metrics across your agent runs, giving you visibility into success rates, execution times, and session patterns. Access analytics from the TUI, web dashboard, CLI, VS Code extension, or programmatically via MCP.

## What Gets Tracked

Kagan collects metrics for every session run:

- **Backend Performance**: Per-agent statistics (success rate, average duration, retry rate)
- **Session Activity**: Daily counts of completed, failed, and cancelled sessions over the last 30 days
- **Timestamps**: When each session ran and how long it took
- **Task Status**: Final outcome of each agent run (completed, failed, cancelled)

All data is stored locally in your Kagan database. Nothing is sent externally.

## Accessing Analytics

### TUI — Kanban Board

Open the analytics modal on the Kanban board:

**Keyboard shortcut:** Press `i` (uppercase I)

The modal shows:
- **Backend Performance** table: Sessions, success %, average duration, retry %
- **Session Activity (30 days)**: Total sessions, breakdown by status, active days, overall success rate

**Actions in modal:**
- `r` — Refresh data
- `e` — Export analytics to JSON (`kagan-analytics.json` in current directory)
- `Esc` — Close modal

### Web Dashboard

Navigate to the **Analytics** page from the main navigation.

The web analytics page includes:
- **KPI Cards**: Quick stats at the top
  - Total Sessions
  - Success Rate
  - Average Duration (weighted by backend)
  - Retry Rate
- **Backend Performance Table**: Detailed per-backend metrics
- **Duration by Backend**: Bar chart showing average session times
- **Session Activity Timeline**: Line chart of daily session counts over 30 days

**Export:** Click the **Export** button in the header to download analytics as JSON.

**Time Range:** Use the dropdown (top right) to filter by last 7, 14, or 30 days.

### CLI — Chat REPL

#### View Analytics

```bash
kagan chat
```

In the chat REPL, use the `/analytics` command:

```
/analytics
```

This opens a Markdown document in your editor showing:
- Backend Performance table
- Session Activity summary

#### Export Analytics

Export analytics to a file:

```
/analytics export
/analytics export /path/to/file.json
```

If no path is specified, exports to `kagan-analytics.json` in the current directory.

### VS Code Extension

Access analytics from the Kagan extension:

**Command Palette** (`Cmd/Ctrl+Shift+P`):
- `Kagan: Show Analytics` — Opens analytics in a Markdown preview
- `Kagan: Export Analytics` — Opens a save dialog to export JSON

Both commands require an active Kagan connection.

### MCP — Programmatic Access

If you're using Kagan's MCP server in another tool, call the analytics tools directly:

```
analytics_backend_stats(project_id, days=30)
```
Returns: Per-backend performance stats (sessions, success rate, duration, retry rate)

```
analytics_session_timeline(project_id, days=30)
```
Returns: Daily session counts (total, completed, failed, cancelled)

```
analytics_export(project_id, days=30)
```
Returns: Combined export with both datasets above

## Understanding the Metrics

### Backend Performance

| Metric | Meaning | Good Range |
|--------|---------|------------|
| **Sessions** | Total runs for this backend | — |
| **Success** | Percentage of runs that completed successfully | 80%+ |
| **Avg Duration** | Average execution time per session | Depends on your workflows |
| **Retry** | Percentage of sessions that were retried | 0–20% |

### Session Activity

| Metric | Meaning |
|--------|---------|
| **Total sessions** | Cumulative runs in the period |
| **Completed** | Sessions that finished successfully |
| **Failed** | Sessions that ended with an error |
| **Cancelled** | Sessions manually stopped |
| **Active days** | Days when you ran at least one session |
| **Success rate** | Overall percentage of completed sessions |

### KPI Cards (Web)

- **Total Sessions**: Count of all session runs in the selected time window
- **Success Rate**: Percentage of sessions that completed (not failed or cancelled)
- **Avg Duration**: Weighted average execution time across all backends (only counts backends with timing data)
- **Retry Rate**: Percentage of sessions that required a retry

## Exporting & Integration

### JSON Export Format

Analytics export as JSON with this structure:

```json
{
  "exported_at": "2026-04-16T09:15:00Z",
  "period_days": 30,
  "backend_stats": [
    {
      "agent_backend": "claude-code",
      "count": 42,
      "success_rate": 0.95,
      "avg_duration_seconds": 185.5,
      "retry_rate": 0.05
    }
  ],
  "session_timeline": [
    {
      "date": "2026-04-16",
      "total": 5,
      "completed": 4,
      "failed": 1,
      "cancelled": 0
    }
  ]
}
```

### Common Use Cases

**Team Dashboards**
Export analytics daily and feed into a team dashboard or analytics tool (Grafana, Datadog, etc.) to track agent performance trends.

**CI Integration**
Include analytics in your build pipeline to validate that agent success rates stay above a threshold:

```bash
kagan /analytics export > analytics.json
jq '.backend_stats[].success_rate' analytics.json | awk '{if ($1 < 0.8) exit 1}'
```

**Cost Analysis**
If cost tracking is enabled, use the export to correlate agent performance with spend.

**Compliance & Audit**
Export analytics as evidence of how often agents ran and their success rates.

## Interpreting Results

### High Retry Rate
If **Retry %** is above 20%, investigate:
- Is a particular agent consistently failing?
- Are tasks timing out?
- Check the task details to see error patterns.

### Low Success Rate
If **Success Rate** is below 80%:
- Examine failed tasks in the TUI (`x` key to delete, but first review the failure message)
- Check if certain backends are underperforming
- Review agent logs to diagnose issues

### Slow Average Duration
If **Avg Duration** is higher than expected:
- Check if tasks are timing out
- Review task complexity (large codebases, complex refactors take longer)
- Compare across backends to see if one agent is consistently slower

### Inactive Days
If **Active days** is much lower than the period (e.g., 5 days in 30), you may not be using Kagan frequently. The data is still valuable for measuring the sessions you *do* run.

## 🔒 Data Privacy & Security

**All analytics data is stored and processed locally. Nothing is sent to external servers.**

### Local Storage
- Analytics are persisted in your local Kagan database (`~/.local/share/kagan/kagan.db` by default)
- Database is SQLite, encrypted by OS-level file permissions
- Data is never transmitted over the network unless you explicitly export it

### No Telemetry
- Kagan does **not** collect or send any usage data to Kagan servers
- No analytics are tracked about your agents, tasks, or runs
- No performance data is reported home
- Your agent runs remain completely private

### Export Control
- You control when and how data is exported
- Exported JSON files are saved only to paths you specify
- No automatic uploads or syncing to cloud services
- Exports are point-in-time snapshots (not continuous sync)

### What's Included in Analytics
Tracked data includes only:
- Session counts per backend
- Success/failure/cancelled counts
- Average execution times per backend
- Retry percentages

**NOT included:**
- Agent prompts or model responses
- Task descriptions or acceptance criteria
- Code changes or diffs
- Tool call details or arguments
- Any user input or conversations

### Compliance
If you need to delete analytics:
1. Clear your Kagan database: `rm ~/.local/share/kagan/kagan.db`
2. Delete any exported JSON files manually
3. Analytics are gone permanently

Use this if you need to comply with data retention policies or privacy regulations.

## Limitations

- Analytics cover the **last 30 days by default** (configurable in export commands)
- **Per-backend metrics** do not distinguish between different task types (all tasks are aggregated)
- **Duration data** includes only backends that report timing; backends without timing data don't affect the average
- Historical data is not archived; if you clear your database, analytics history is lost

## Troubleshooting

### "No data yet"
You haven't run any sessions yet. Run a task with any agent, and analytics will populate after the first session completes.

### Metrics show 0% success
- Confirm tasks have actually completed (check TUI board status)
- Verify the time window matches when you ran sessions (use the date picker on web dashboard)

### Export fails
- Ensure you have write permissions in the target directory
- Check that your project has an active repository linked (`/project` in CLI, or Projects page in web)

### Missing backends
If a backend you've used isn't showing in the Backend Performance table, it may have had zero runs in the selected time window.
