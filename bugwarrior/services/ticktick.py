import logging
import typing_extensions

import requests
from dateutil.parser import parse as parse_date

from bugwarrior import config
from bugwarrior.services import Client, Issue, Service

log = logging.getLogger(__name__)


class TickTickConfig(config.ServiceConfig):
    """TickTick service configuration following pydantic v2 schema."""

    service: typing_extensions.Literal["ticktick"]

    # Authentication - API token only
    token: str = ""

    # Task filtering options
    project_filter: str = ""

    # Label/tag handling
    import_labels_as_tags: bool = False
    label_template: str = "{{tag}}"

    char_open_bracket: str = "("
    char_close_bracket: str = ")"


class TickTickIssue(Issue):
    """TickTick task to Taskwarrior issue mapping."""

    # User Defined Attributes (UDAs)
    ID = "ticktickid"
    CONTENT = "ticktickcontent"
    TITLE = "tickticktitle"
    DESCRIPTION = "ticktickdesc"
    DUE = "ticktickduedate"
    START = "ticktickstartdate"
    PROJECT = "ticktickproject"
    URL = "ticktickurl"
    PRIORITY = "ticktickpriority"
    KIND = "ticktickkind"

    # Priority mapping: TickTick priority to Taskwarrior priority
    PRIORITY_MAP = {
        0: None,  # None
        1: "L",  # Low
        3: "M",  # Medium
        5: "H",  # High
    }

    # User Defined Attributes schema
    UDAS = {
        ID: {"type": "string", "label": "TickTick ID"},
        CONTENT: {"type": "string", "label": "TickTick Content"},
        TITLE: {"type": "string", "label": "TickTick Title"},
        DESCRIPTION: {"type": "string", "label": "TickTick Description"},
        DUE: {"type": "date", "label": "TickTick Due Date"},
        START: {"type": "date", "label": "TickTick Start Date"},
        PROJECT: {"type": "string", "label": "TickTick Project"},
        URL: {"type": "string", "label": "TickTick URL"},
        PRIORITY: {"type": "string", "label": "TickTick Priority"},
        KIND: {"type": "string", "label": "TickTick Kind"},
    }

    # Unique identifier for TickTick tasks
    UNIQUE_KEY = (ID,)

    # replace characters that cause escaping issues like [] and "
    # this is a workaround for https://github.com/ralphbean/taskw/issues/172
    def _unescape_content(self, content):
        return (
            content.replace('"', "'")  # prevent &dquote; in task details
            .replace("[", self.config.char_open_bracket)  # prevent &open; and &close;
            .replace("]", self.config.char_close_bracket)
        )

    def _get_task_url(self):
        return f'https://ticktick.com/webapp/#p/{self.extra.get("project_id")}/tasks/{self.record["id"]}'

    def to_taskwarrior(self):
        """Convert TickTick task to Taskwarrior format."""

        task = {
            "project": self.extra.get("project"),
            "priority": self.get_priority(),
            "annotations": self.extra.get("annotations", []),
            "status": ("completed" if self.record.get("status") == 2 else "pending"),
            self.ID: self.record["id"],
            self.CONTENT: self._unescape_content(self.record.get("content", "")),
            self.TITLE: self._unescape_content(self.record.get("title")),
            self.DESCRIPTION: self._unescape_content(self.record.get("desc", "")),
            self.URL: self._get_task_url(),
            self.PRIORITY: self.record.get("priority", 0),
            self.KIND: self.record.get("kind"),
        }

        # Handle due date
        if self.record.get("dueDate"):
            due_date = self.record["dueDate"]
            if isinstance(due_date, str):
                due_date = parse_date(due_date)
            task["due"] = due_date
            task[self.DUE] = due_date

        # Handle start date
        if self.record.get("startDate"):
            start_date = self.record["startDate"]
            if isinstance(start_date, str):
                start_date = parse_date(start_date)
            task[self.START] = start_date

        # Handle tags if enabled
        if self.config.import_labels_as_tags and self.record.get("tags"):
            task["tags"] = [
                self.config.label_template.replace("{{tag}}", tag)
                for tag in self.record["tags"]
            ]

        return task

    def get_default_description(self):
        """Generate default description for the task."""

        return self.build_default_description(
            title=self._unescape_content(self.record["title"]),
            url=self._get_task_url(),
            number=self.record["id"],
            cls="task",
        )


class TickTickClient(Client):
    """TickTick API client for fetching projects and tasks."""

    def __init__(self, access_token, project_filter=""):
        self.access_token = access_token
        self.project_filter = project_filter
        self.base_url = "https://api.ticktick.com/open/v1"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def get_projects(self):
        """Fetch all projects from TickTick API."""
        url = f"{self.base_url}/project"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"Failed to fetch TickTick projects: {e}")
            return []

    def get_project_data(self, project_id):
        """Fetch project with tasks and columns using project ID."""
        url = f"{self.base_url}/project/{project_id}/data"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"Failed to fetch data for project {project_id}: {e}")
            return None

    def get_issues(self):
        """Main method to fetch all issues based on configuration."""
        projects = self.get_projects()
        if not projects:
            return []

        # get Inbox tasks
        # "inbox" is a special project id not returned in the project list
        projects.append({"id": "inbox"})

        # Filter projects if project_filter is specified
        if self.project_filter:
            project_ids = [p.strip() for p in self.project_filter.split(",")]
            projects = [p for p in projects if p["id"] in project_ids]

        for project in projects:
            project_data = self.get_project_data(project["id"])
            if not project_data:
                continue

            # Extract tasks from project data
            tasks = project_data.get("tasks", [])
            for task in tasks:
                # Add project context to each task
                task["project"] = project
                yield task


class TickTickService(Service):
    """TickTick service implementation with API token authentication."""

    API_VERSION = 1.0
    ISSUE_CLASS = TickTickIssue
    CONFIG_SCHEMA = TickTickConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get access token (API token only)
        access_token = self.get_access_token()

        # Initialize client with access token and project filter
        project_filter = (
            self.config.project_filter if self.config.project_filter else ""
        )
        self.client = TickTickClient(
            access_token=access_token, project_filter=project_filter
        )

    @staticmethod
    def get_keyring_service(config):
        """Get keyring service name for secret storage."""
        return "ticktick://"

    def get_access_token(self):
        """Handle authentication - API token only."""
        if not self.config.token:
            raise Exception(
                "No API token provided. Please configure 'token' with your TickTick API token."
            )
        return self.config.token

    def issues(self):
        """Generator yielding TickTickIssue instances."""
        project_index = {}

        for issue_data in self.client.get_issues():
            project_id = issue_data.get("project", {}).get("id", "unknown")
            project_name = issue_data.get("project", {}).get("name", "Inbox")

            if project_id not in project_index:
                project_index[project_id] = project_name

            extra = {
                "project_id": project_id,
                "project": project_name,
                "annotations": [],
            }

            yield self.get_issue_for_record(issue_data, extra)

    def annotations(self, user_index, issue):
        """Handle task comments/annotations if supported."""
        # TickTick doesn't support comments/annotations
        return []
