import copy
from unittest import mock

from bugwarrior.services.ticktick import TickTickClient, TickTickService

from .base import AbstractServiceTest, ServiceTest


class TestTickTickIssue(AbstractServiceTest, ServiceTest):

    SERVICE_CONFIG = {
        "service": "ticktick",
        "token": "TEST_API_TOKEN",
    }
    # Base test record - mock TickTick task data
    test_record = {
        "id": "1111111111111111",
        "projectId": "2222222222222222",
        "sortOrder": -5497558138880,
        "title": "TESTTASK",
        "content": "TESTTASKDESCRIPTION",
        "startDate": "2025-06-30T00:00:00Z",
        "dueDate": "2025-07-01T00:00:00Z",
        "timeZone": "America/Toronto",
        "isAllDay": True,
        "priority": 3,  # 0=None, 1=Low, 3=Medium, 5=High
        "status": 0,  # 0 = Normal, 2 = Completed
        "etag": "xqs0y4fn",
        "kind": "TEXT",
        "tags": ["TESTTAG"],
        "project": {
            "id": '2222222222222222', 
            'name': 'TESTPROJECT',
            'sortOrder': -8796093153280,
            'viewMode': 'list',
            'kind': 'TASK'
        }
    }

    test_extra = {"project_id": "2222222222222222", "project": "TESTPROJECT", "annotations": []}

    test_project = {
        "id": "2222222222222222",
        "name": "TESTPROJECT",
        "sortOrder": -8796093153280,
        "viewMode": "list",
        "kind": "TASK"
    }

    def setUp(self):
        super().setUp()

        self.service = self.get_mock_service(TickTickService)
        self.service.client = mock.MagicMock(spec=TickTickClient)

    def get_mock_issue(self, record=None, extra=None):
        """Create a mock issue for testing."""
        record = record if record is not None else self.test_record.copy()
        extra = extra if extra is not None else self.test_extra.copy()
        return self.service.get_issue_for_record(record, extra)

    def test_to_taskwarrior(self):
        """Test basic task transformation."""
        issue = self.get_mock_issue()
        task = issue.to_taskwarrior()

        self.assertEqual(task["project"], "TESTPROJECT")
        self.assertEqual(task["priority"], "M")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["ticktickid"], "1111111111111111")
        self.assertEqual(task["ticktickcontent"], "TESTTASKDESCRIPTION")
        self.assertEqual(task["tickticktitle"], "TESTTASK")
        self.assertEqual(
            task["ticktickurl"], "https://ticktick.com/webapp/#p/2222222222222222/tasks/1111111111111111"
        )
        self.assertEqual(task["ticktickpriority"], 3)

    def test_to_taskwarrior_with_priority(self):
        """Test priority mapping."""
        # Test Low priority
        record = copy.deepcopy(self.test_record)
        record["priority"] = 1
        issue = self.get_mock_issue(record=record)
        task = issue.to_taskwarrior()
        self.assertEqual(task["priority"], "L")

        # Test High priority
        record["priority"] = 5
        issue = self.get_mock_issue(record=record)
        task = issue.to_taskwarrior()
        self.assertEqual(task["priority"], "H")

        # Test No priority
        record["priority"] = 0
        issue = self.get_mock_issue(record=record)
        task = issue.to_taskwarrior()
        self.assertEqual(task["priority"], None)

    def test_to_taskwarrior_with_tags(self):
        """Test tag import when enabled."""
        # Test with import_labels_as_tags disabled (default)
        issue = self.get_mock_issue()
        task = issue.to_taskwarrior()
        self.assertNotIn("tags", task)

        # Test with import_labels_as_tags enabled
        config = copy.deepcopy(self.SERVICE_CONFIG)
        config["import_labels_as_tags"] = True
        self.service = self.get_mock_service(TickTickService, config_overrides=config)
        issue = self.get_mock_issue()
        task = issue.to_taskwarrior()
        self.assertEqual(task["tags"], ["TESTTAG"])

        # Test with custom label template
        config["label_template"] = "ticktick_{{tag}}"
        self.service = self.get_mock_service(TickTickService, config_overrides=config)
        issue = self.get_mock_issue()
        task = issue.to_taskwarrior()
        self.assertEqual(task["tags"], ["ticktick_TESTTAG"])

    def test_to_taskwarrior_completed_task(self):
        """Test completed task transformation."""
        record = copy.deepcopy(self.test_record)
        record["status"] = 2  # Completed
        issue = self.get_mock_issue(record=record)
        task = issue.to_taskwarrior()
        self.assertEqual(task["status"], "completed")

    def test_to_taskwarrior_due_dates(self):
        """Test due date handling."""
        issue = self.get_mock_issue()
        task = issue.to_taskwarrior()

        # Check that due date is parsed correctly
        self.assertIsNotNone(task["due"])
        self.assertIsNotNone(task["ticktickduedate"])

        # Check start date
        self.assertIsNotNone(task["ticktickstartdate"])

    def test_to_taskwarrior_no_dates(self):
        """Test task without dates."""
        record = copy.deepcopy(self.test_record)
        record["dueDate"] = None
        record["startDate"] = None
        issue = self.get_mock_issue(record=record)
        task = issue.to_taskwarrior()

        self.assertNotIn("due", task)
        self.assertNotIn("scheduled", task)

    def test_get_default_description(self):
        """Test default description generation."""
        issue = self.get_mock_issue()
        description = issue.get_default_description()

        self.assertIn("TESTTASK", description)
        self.assertIn("https://ticktick.com/webapp/#p/2222222222222222/tasks/1111111111111111", description)
        self.assertIn("1111111111111111", description)

    def test_issues(self):
        """Test issue generation with mocked API responses."""
        # Mock the client's get_issues method
        mock_tasks = [
            copy.deepcopy(self.test_record),
            {
                "id": "3333333333333333",
                "title": "SECONDTASK",
                "content": "SECONDTASKDESCRIPTION",
                "projectId": "2222222222222222",
                "status": 0,
                "priority": 1,
                "dueDate": None,
                "startDate": None,
                "createdTime": "2025-07-02T08:00:00Z",
                "tags": ["TAG1", "TAG2"],
                "url": "https://ticktick.com/task/3333333333333333",
            },
        ]

        self.service.client.get_issues.return_value = mock_tasks

        issues = list(self.service.issues())
        self.assertEqual(len(issues), 2)

        # Test first issue
        issue1 = issues[0]
        self.assertEqual(issue1.record["id"], "1111111111111111")
        self.assertEqual(issue1.record["title"], "TESTTASK")

        # Test second issue
        issue2 = issues[1]
        self.assertEqual(issue2.record["id"], "3333333333333333")
        self.assertEqual(issue2.record["title"], "SECONDTASK")

    def test_client_get_projects(self):
        """Test TickTickClient get_projects method."""
        client = TickTickClient("TEST_TOKEN")

        # Mock the requests.get call
        with mock.patch('requests.get') as mock_get:
            mock_response = mock.MagicMock()
            mock_response.json.return_value = [self.test_project]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            projects = client.get_projects()

            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]["id"], "2222222222222222")
            self.assertEqual(projects[0]["name"], "TESTPROJECT")

    def test_client_get_project_data(self):
        """Test TickTickClient get_project_data method."""
        client = TickTickClient("TEST_TOKEN")

        # Mock the requests.get call
        with mock.patch('requests.get') as mock_get:
            mock_response = mock.MagicMock()
            mock_response.json.return_value = {
                "project": self.test_project,
                "tasks": [self.test_record],
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            project_data = client.get_project_data("2222222222222222")

            self.assertIsNotNone(project_data)
            self.assertEqual(project_data["project"]["id"], "2222222222222222")
            self.assertEqual(len(project_data["tasks"]), 1)

    def test_client_get_issues_with_project_filter(self):
        """Test TickTickClient get_issues with project filtering."""
        client = TickTickClient("TEST_TOKEN", project_filter="2222222222222222")

        # Mock get_projects and get_project_data
        with (
            mock.patch.object(client, 'get_projects') as mock_projects,
            mock.patch.object(client, 'get_project_data') as mock_data,
        ):
            mock_projects.return_value = [
                self.test_project,
                {
                    "id": "4444444444444444",
                    "name": "OTHERPROJECT",
                    "color": "#00FF00",
                    "sortType": 0,
                },
            ]

            mock_data.return_value = {
                "project": self.test_project,
                "tasks": [self.test_record],
            }

            issues = list(client.get_issues())

            # Should only return tasks from the filtered project
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["projectId"], "2222222222222222")

            # Should only call get_project_data for the filtered project
            mock_data.assert_called_once_with("2222222222222222")

    def test_client_get_issues_no_filter(self):
        """Test TickTickClient get_issues without project filtering."""
        client = TickTickClient("TEST_TOKEN")

        # Mock get_projects and get_project_data
        with (
            mock.patch.object(client, 'get_projects') as mock_projects,
            mock.patch.object(client, 'get_project_data') as mock_data,
        ):
            mock_projects.return_value = [
                self.test_project,
                {
                    "id": "4444444444444444",
                    "name": "OTHERPROJECT",
                },
            ]

            mock_data.return_value = {
                "project": self.test_project,
                "tasks": [self.test_record],
            }

            issues = list(client.get_issues())

            # Should return tasks from all projects
            self.assertEqual(len(issues), 3)

            # Should call get_project_data for both projects plus inbox
            self.assertEqual(mock_data.call_count, 3)

    def test_service_authentication(self):
        """Test TickTickService authentication flow."""
        # Test API token authentication
        access_token = self.service.get_access_token()
        self.assertEqual(access_token, "TEST_API_TOKEN")

    def test_service_authentication_no_token(self):
        """Test TickTickService authentication without token."""
        # Create service with no token - should raise exception during initialization
        config = copy.deepcopy(self.SERVICE_CONFIG)
        config["token"] = ""

        # Should raise exception when no token provided during service initialization
        with self.assertRaises(Exception) as context:
            self.get_mock_service(TickTickService, config_overrides=config)

        self.assertIn("No API token provided", str(context.exception))

    def test_service_annotations(self):
        """Test TickTickService annotations method."""
        # TickTick doesn't support annotations/comments in the current API
        # This test verifies the method returns empty list
        user_index = {}
        issue = {"id": "1111111111111111"}

        annotations = self.service.annotations(user_index, issue)
        self.assertEqual(annotations, [])
