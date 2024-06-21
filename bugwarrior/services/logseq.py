import logging

import requests
import typing_extensions

import re
from datetime import datetime

from bugwarrior import config
from bugwarrior.services import IssueService, Issue, ServiceClient

log = logging.getLogger(__name__)


class LogseqConfig(config.ServiceConfig):
    service: typing_extensions.Literal["logseq"]
    host: str = "localhost"
    port: int = 12315
    token: str = ""
    task_state: str = "DOING, TODO, NOW, LATER, IN-PROGRESS, WAIT, WAITING"
    char_open_link: str = "【"
    char_close_link: str = "】"
    char_open_bracket: str = "〈"
    char_close_bracket: str = "〉"


class LogseqClient(ServiceClient):
    def __init__(self, host, port, token, filter):
        self.host = host
        self.port = port
        self.token = token
        self.filter = filter

        self.headers = {
            "Authorization": "Bearer " + self.token,
            "content-type": "application/json; charset=utf-8",
        }

        self.project = None

    def _datascript_query(self, query):
        try:
            response = requests.post(
                f"http://{self.host}:{self.port}/api",
                headers=self.headers,
                json={"method": "logseq.DB.datascriptQuery", "args": [query]},
            )
            return self.json_response(response)
        except requests.exceptions.ConnectionError as ce:
            log.fatal("Unable to connect to Logseq HTTP APIs server. %s", ce)
            exit()

    def _get_current_graph(self):
        try:
            response = requests.post(
                f"http://{self.host}:{self.port}/api",
                headers=self.headers,
                json={"method": "logseq.getCurrentGraph", "args": []},
            )
            return self.json_response(response)
        except requests.exceptions.ConnectionError as ce:
            log.fatal("Unable to connect to Logseq HTTP APIs server. %s", ce)
            exit()

    def get_graph_name(self):
        graph = self._get_current_graph()
        return graph["name"] if graph else None

    def get_issues(self):
        task_filter = self.filter.replace(" ", "").replace(",", '" "')
        return self._datascript_query(
            f"""
            [:find (pull ?b [*])
                :where [?b :block/marker ?marker]
                [(contains? #{{\"{task_filter}\"}} ?marker)]
            ]
        """
        )


class LogseqIssue(Issue):
    ID = "logseqid"
    UUID = "logsequuid"
    STATE = "logseqstate"
    TITLE = "logseqtitle"
    SCHEDULED = "logseqscheduled"
    DEADLINE = "logseqdeadline"
    DONE = "logseqdone"
    URI = "logsequri"

    UDAS = {
        ID: {
            "type": "string",
            "label": "Logseq ID",
        },
        UUID: {
            "type": "string",
            "label": "Logseq UUID",
        },
        STATE: {
            "type": "string",
            "label": "Logseq State",
        },
        TITLE: {
            "type": "string",
            "label": "Logseq Title",
        },
        SCHEDULED: {
            "type": "date",
            "label": "Logseq Scheduled",
        },
        DEADLINE: {
            "type": "date",
            "label": "Logseq Deadline",
        },
        DONE: {
            "type": "date",
            "label": "Logseq Done",
        },
        URI: {
            "type": "string",
            "label": "Logseq URI",
        },
    }

    UNIQUE_KEY = (ID, UUID)

    # map A B C priority to H M L
    PRIORITY_MAP = {
        "A": "H",
        "B": "M",
        "C": "L",
    }

    STATE_MAP = {
        "IN-PROGRESS": "pending",
        "DOING": "pending",
        "TODO": "pending",
        "NOW": "pending",
        "LATER": "pending",
        "WAIT": "waiting",
        "WAITING": "waiting",
        "DONE": "completed",
        "CANCELED": "deleted",
        "CANCELLED": "deleted",
    }

    # replace characters that cause escaping issues like [] and "
    def _unescape_content(self, content):
        return (
            content.replace('"', "'")  # prevent &dquote; in task details
            .replace("[[", self.config.char_open_link)  # alternate brackets for linked items
            .replace("]]", self.config.char_close_link)
            .replace("[", self.config.char_open_bracket)  # prevent &open; and &close;
            .replace("]", self.config.char_close_bracket)
        )

    # get a optimized and
    def get_formated_title(self):
        # use first line only and remove priority
        first_line = (
            self.record["content"]
            .split("\n")[0]  # only use first line
            .replace("[#A] ", "")
            .replace("[#B] ", "")
            .replace("[#C] ", "")
        )
        return self._unescape_content(first_line)

    # get a list of tags from the task content
    def get_tags_from_content(self):
        # this includes #tagname, but ignores tags that are in the #[[tag name]] format
        tags = re.findall(
            r"(#[^" + self.config.char_open_link + r"^\s]+)", self.get_formated_title()
        )
        return tags

    # get a list of annotations form the content
    def get_annotations_from_content(self):
        annotations = []
        scheduled_date = None
        deadline_date = None
        for line in self.record["content"].split("\n"):
            # handle special annotations
            if line.startswith("SCHEDULED: "):
                scheduled_date = self.get_scheduled_date(line)
            elif line.startswith("DEADLINE: "):
                deadline_date = self.get_scheduled_date(line)
            else:
                annotations.append(self._unescape_content(line))
        annotations.pop(0)  # remove first line
        return annotations, scheduled_date, deadline_date

    def get_url(self):
        return f'logseq://graph/{self.extra["graph"]}?block-id={self.record["uuid"]}'

    def get_logseq_state(self):
        return self.record["marker"]

    def get_scheduled_date(self, scheduled):
        # format is <YYYY-MO-DD DAY HH:MM .+1d>
        # e.g. <2024-06-20 Thu 10:55 .+1d>
        date_split = (
            scheduled.replace("DEADLINE: <", "")
            .replace("SCHEDULED: <", "")
            .replace(">", "")
            .split(" ")
        )
        date = ""
        date_format = ""
        if len(date_split) == 2:  # <date day>
            date = date_split[0]
            date_format = "%Y-%m-%d"
        elif len(date_split) == 3 and (date_split[2][0] in ("+", ".")):  # <date day repeat>
            date = date_split[0]
            date_format = "%Y-%m-%d"
        elif len(date_split) == 3:  # <date day time>
            date = date_split[0] + " " + date_split[2]
            date_format = "%Y-%m-%d %H:%M"
        elif len(date_split) == 4:  # <date date time repeat>
            date = date_split[0] + " " + date_split[2]
            date_format = "%Y-%m-%d %H:%M"
        else:
            log.warning(f"Could not determine date format from {scheduled}")
            return None

        try:
            return datetime.strptime(date, date_format)
        except ValueError:
            log.warning(f"Could not parse date {date} from {scheduled}")
        return None

    def to_taskwarrior(self):
        annotations, scheduled_date, deadline_date = self.get_annotations_from_content()
        return {
            "project": self.extra["graph"],
            "priority": (
                self.PRIORITY_MAP[self.record["priority"]]
                if "priority" in self.record
                else None
            ),
            "annotations": annotations,
            "tags": self.get_tags_from_content(),
            "due": deadline_date,
            "scheduled": scheduled_date,
            "status": self.STATE_MAP[self.get_logseq_state()],
            self.ID: self.record["id"],
            self.UUID: self.record["uuid"],
            self.STATE: self.record["marker"],
            self.TITLE: self.get_formated_title(),
            self.SCHEDULED: scheduled_date,
            self.DEADLINE: deadline_date,
            self.URI: self.get_url(),
        }

    def get_default_description(self):
        return self.build_default_description(
            title=self.get_formated_title(),
            url=self.get_url(),
            number=self.record["id"],
            cls="issue",
        )


class LogseqService(IssueService):
    ISSUE_CLASS = LogseqIssue
    CONFIG_SCHEMA = LogseqConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.client = LogseqClient(
            host=self.config.host,
            port=self.config.port,
            token=self.config.token,
            filter=self.config.task_state,
        )

    def get_owner(self, issue):
        # Issue assignment hasn't been implemented yet.
        raise NotImplementedError(
            "This service has not implemented support for 'only_if_assigned'."
        )

    def issues(self):
        graph_name = self.client.get_graph_name()
        for issue in self.client.get_issues():
            extra = {}
            extra["graph"] = graph_name
            yield self.get_issue_for_record(issue[0], extra)
