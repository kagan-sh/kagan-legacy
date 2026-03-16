from dataclasses import dataclass

from textual.message import Message

from kagan.core.enums import Priority, TaskStatus, WorkMode
from kagan.core.models import Project, Task

__all__ = [
    "BranchSelected",
    "ChatCloseRequested",
    "ChatRequested",
    "ChatSubmitRequested",
    "DiffActionRequested",
    "DiffFileSelected",
    "DiffsLoaded",
    "MentionCompleted",
    "MentionDismissed",
    "MentionKeyPressed",
    "MentionQuery",
    "OfflineBannerDismissed",
    "OfflineReconnectRequested",
    "OnboardingCompleted",
    "ProjectOpened",
    "RepoPickerRequested",
    "ReviewRequested",
    "SearchPresetSelected",
    "SearchQueryChanged",
    "SlashCompletionCompleted",
    "SlashCompletionDismissed",
    "TaskDeleted",
    "TaskDuplicateRequested",
    "TaskOpened",
    "TaskPeekRequested",
    "TaskSelected",
    "TaskStatusMoveRequested",
    "TaskSubmitted",
]


@dataclass
class ProjectOpened(Message):
    project: Project


@dataclass
class OnboardingCompleted(Message):
    config: object


@dataclass
class TaskSelected(Message):
    task: Task


@dataclass
class SearchPresetSelected(Message):
    query: str


@dataclass
class SearchQueryChanged(Message):
    query: str


@dataclass
class TaskOpened(Message):
    task: Task


@dataclass
class DiffFileSelected(Message):
    repo_id: str
    entry: object


@dataclass
class DiffActionRequested(Message):
    action: str


@dataclass
class DiffsLoaded(Message):
    repo_count: int
    changed_file_count: int
    load_failed: bool = False

    @property
    def has_diffs(self) -> bool:
        return self.changed_file_count > 0


@dataclass
class TaskPeekRequested(Message):
    task: Task


@dataclass
class TaskSubmitted(Message):
    title: str
    description: str
    priority: Priority
    execution_mode: WorkMode
    agent_backend: str | None
    launcher: str | None
    base_branch: str | None


@dataclass
class ChatSubmitRequested(Message):
    text: str


@dataclass
class ChatCloseRequested(Message):
    index: int


@dataclass
class MentionCompleted(Message):
    task_id: str


@dataclass
class MentionQuery(Message):
    query: str
    start_index: int
    end_index: int


@dataclass
class MentionDismissed(Message):
    pass


@dataclass
class MentionKeyPressed(Message):
    key: str


@dataclass
class SlashCompletionCompleted(Message):
    command: str


@dataclass
class SlashCompletionDismissed(Message):
    pass


@dataclass
class OfflineReconnectRequested(Message):
    pass


@dataclass
class OfflineBannerDismissed(Message):
    pass


@dataclass
class TaskDeleted(Message):
    task_id: str


@dataclass
class TaskDuplicateRequested(Message):
    task: Task


@dataclass
class TaskStatusMoveRequested(Message):
    task: Task
    target: TaskStatus


@dataclass
class ReviewRequested(Message):
    task: Task


@dataclass
class RepoPickerRequested(Message):
    pass


@dataclass
class ChatRequested(Message):
    pass


@dataclass
class BranchSelected(Message):
    branch: str
