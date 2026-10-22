from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.main import app


def _matches(document, query):
    return all(document.get(key) == value for key, value in query.items())


class MemoryCursor(list):
    def sort(self, key, direction):
        super().sort(key=lambda item: item.get(key), reverse=direction < 0)
        return self


class MemoryCollection:
    def __init__(self, name):
        self.name = name
        self.documents = []

    def create_index(self, *args, **kwargs):
        return kwargs.get("name", "index")

    def find_one(self, query):
        found = next((item for item in self.documents if _matches(item, query)), None)
        return deepcopy(found) if found is not None else None

    def find(self, query):
        return MemoryCursor(deepcopy([item for item in self.documents if _matches(item, query)]))

    def insert_one(self, document):
        candidate = deepcopy(document)
        if self.name == "users" and any(
            item.get("username_normalized") == candidate.get("username_normalized")
            for item in self.documents
        ):
            raise DuplicateKeyError("duplicate username")
        if self.name == "surveys" and any(
            item.get("share_slug") == candidate.get("share_slug")
            for item in self.documents
        ):
            raise DuplicateKeyError("duplicate share slug")
        if self.name == "responses" and candidate.get("submission_key") is not None and any(
            item.get("survey_id") == candidate.get("survey_id")
            and item.get("submission_key") == candidate.get("submission_key")
            for item in self.documents
        ):
            raise DuplicateKeyError("duplicate submission")
        candidate.setdefault("_id", ObjectId())
        self.documents.append(candidate)
        document["_id"] = candidate["_id"]
        return SimpleNamespace(inserted_id=candidate["_id"])

    def update_one(self, query, update):
        for item in self.documents:
            if _matches(item, query):
                item.update(deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def replace_one(self, query, replacement):
        for index, item in enumerate(self.documents):
            if _matches(item, query):
                self.documents[index] = deepcopy(replacement)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class MemoryDatabase:
    def __init__(self):
        self.users = MemoryCollection("users")
        self.surveys = MemoryCollection("surveys")
        self.responses = MemoryCollection("responses")

    def command(self, name):
        assert name == "ping"
        return {"ok": 1}


@pytest.fixture
def api():
    database = MemoryDatabase()
    app.state.mongo_database = database
    app.state.mongo_client = None
    with TestClient(app) as client:
        yield client, database
    app.state.mongo_database = None


def register_and_login(client, username):
    registered = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert registered.status_code == 201
    logged_in = client.post("/auth/login", json={"username": username.upper(), "password": "secret123"})
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def choice_question(question_id, order, multiple=False, required=True):
    return {
        "question_id": question_id,
        "type": "multiple_choice" if multiple else "single_choice",
        "title": question_id,
        "required": required,
        "order": order,
        "options": [
            {"option_id": "a", "label": "A", "order": 1},
            {"option_id": "b", "label": "B", "order": 2},
        ],
        "validation": {},
        "jump_rules": [],
    }


def answer(question_id, question_type, value):
    return {"question_id": question_id, "type": question_type, "value": value}


def create_and_publish(client, headers, questions, **settings):
    payload = {"title": "Course survey", "questions": questions, **settings}
    created = client.post("/surveys", headers=headers, json=payload)
    assert created.status_code == 201
    survey_id = created.json()["survey_id"]
    published = client.post(f"/surveys/{survey_id}/publish", headers=headers)
    assert published.status_code == 200
    return survey_id, published.json()["share_slug"]


def test_registration_login_and_owner_isolation(api):
    client, database = api
    alice = register_and_login(client, "Alice")
    duplicate = client.post("/auth/register", json={"username": " alice ", "password": "secret123"})
    assert duplicate.status_code == 409
    assert database.users.documents[0]["password_hash"] != "secret123"
    assert "secret123" not in database.users.documents[0]["password_hash"]

    created = client.post("/surveys", headers=alice, json={"title": "Mine"})
    survey_id = created.json()["survey_id"]
    bob = register_and_login(client, "bob")
    assert client.get(f"/surveys/{survey_id}", headers=bob).status_code == 404
    assert client.get("/surveys", headers=bob).json() == []
    assert len(client.get("/surveys", headers=alice).json()) == 1


def test_publish_validation_versioning_and_close(api):
    client, _ = api
    owner = register_and_login(client, "owner")
    draft = client.post("/surveys", headers=owner, json={"title": "Empty"})
    invalid = client.post(f"/surveys/{draft.json()['survey_id']}/publish", headers=owner)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["errors"][0]["code"] == "empty_survey"

    survey_id, slug = create_and_publish(client, owner, [choice_question("q1", 1)])
    edited = client.patch(
        f"/surveys/{survey_id}", headers=owner, json={"questions": [choice_question("q2", 1)]}
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["current_version"] == 2
    assert body["published_version"] == 1
    assert body["versions"][0]["questions"][0]["question_id"] == "q1"
    assert body["versions"][1]["questions"][0]["question_id"] == "q2"

    closed = client.post(f"/surveys/{survey_id}/close", headers=owner)
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.get(f"/surveys/share/{slug}").status_code == 410


def test_conditional_navigation_submission_and_duplicate_policy(api):
    client, database = api
    owner = register_and_login(client, "jump-owner")
    q1 = choice_question("q1", 1)
    q1["jump_rules"] = [{
        "rule_id": "skip-q2", "priority": 1,
        "condition": {"operator": "equals", "value": "a"},
        "target": {"type": "question", "question_id": "q3"},
    }]
    q2 = {"question_id": "q2", "type": "text_input", "title": "Skipped", "required": True, "order": 2, "validation": {}, "jump_rules": []}
    q3 = {"question_id": "q3", "type": "text_input", "title": "Finish", "required": True, "order": 3, "validation": {"min_length": 2}, "jump_rules": []}
    survey_id, slug = create_and_publish(client, owner, [q1, q2, q3])
    assert client.get(f"/surveys/share/{slug}").status_code == 200
    assert client.post(f"/surveys/share/{slug}/next", json={"question_id": "q1", "answers": {}}).status_code == 401
    assert client.post(f"/surveys/share/{slug}/submit", json={"answers": {}}).status_code == 401
    filler = register_and_login(client, "filler")
    q1_answer = answer("q1", "single_choice", "a")

    navigation = client.post(
        f"/surveys/share/{slug}/next", headers=filler,
        json={"question_id": "q1", "answers": {"q1": q1_answer}},
    )
    assert navigation.status_code == 200
    assert navigation.json() == {"action": "goto_question", "question_id": "q3", "matched_rule_id": "skip-q2"}

    invalid_navigation = client.post(
        f"/surveys/share/{slug}/next", headers=filler,
        json={"question_id": "q1", "answers": {"q1": answer("q1", "single_choice", "unknown")}},
    )
    assert invalid_navigation.status_code == 422
    assert invalid_navigation.json()["detail"]["code"] == "invalid_answer_option"

    answers = {"q1": q1_answer, "q3": answer("q3", "text_input", "ok")}
    submitted = client.post(f"/surveys/share/{slug}/submit", headers=filler, json={"answers": answers})
    assert submitted.status_code == 201
    assert submitted.json()["path"] == ["q1", "q3"]
    assert database.responses.documents[0]["survey_id"] == ObjectId(survey_id)

    duplicate = client.post(f"/surveys/share/{slug}/submit", headers=filler, json={"answers": answers})
    assert duplicate.status_code == 409

    forged = {**answers, "q2": answer("q2", "text_input", "should fail")}
    other = register_and_login(client, "other-filler")
    rejected = client.post(f"/surveys/share/{slug}/submit", headers=other, json={"answers": forged})
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["errors"][0]["code"] == "answer_not_on_path"


def test_all_question_statistics(api):
    client, _ = api
    owner = register_and_login(client, "stats-owner")
    questions = [
        choice_question("single", 1),
        choice_question("multi", 2, multiple=True),
        {"question_id": "text", "type": "text_input", "title": "Text", "required": True, "order": 3, "validation": {}, "jump_rules": []},
        {"question_id": "number", "type": "number_input", "title": "Number", "required": True, "order": 4, "validation": {}, "jump_rules": []},
    ]
    survey_id, slug = create_and_publish(client, owner, questions, allow_anonymous=True)
    values = [("one", "a", ["a", "b"], "first", 10), ("two", "b", ["b"], "second", 20)]
    for username, single, multi, text, number in values:
        filler = register_and_login(client, username)
        answers = {
            "single": answer("single", "single_choice", single),
            "multi": answer("multi", "multiple_choice", multi),
            "text": answer("text", "text_input", text),
            "number": answer("number", "number_input", number),
        }
        assert client.post(f"/surveys/share/{slug}/submit", headers=filler, json={"answers": answers}).status_code == 201

    statistics = client.get(f"/surveys/{survey_id}/statistics", headers=owner)
    assert statistics.status_code == 200
    data = statistics.json()
    assert data["response_count"] == 2
    assert data["questions"]["single"]["option_counts"] == {"a": 1, "b": 1}
    assert data["questions"]["multi"]["option_counts"] == {"a": 1, "b": 2}
    assert data["questions"]["text"]["answers"] == ["first", "second"]
    assert data["questions"]["number"]["average"] == 15
    assert "respondent_user_id" not in statistics.json()
    assert client.get(f"/surveys/{survey_id}/statistics", headers=register_and_login(client, "intruder")).status_code == 404


def test_deadline_blocks_published_share_and_submission(api):
    client, _ = api
    owner = register_and_login(client, "deadline-owner")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    created = client.post(
        "/surveys",
        headers=owner,
        json={"title": "Expired", "deadline_at": past, "questions": [choice_question("q1", 1)]},
    )
    assert created.status_code == 201
    survey_id = created.json()["survey_id"]
    published = client.post(f"/surveys/{survey_id}/publish", headers=owner)
    assert published.status_code == 200
    slug = published.json()["share_slug"]
    assert client.get(f"/surveys/share/{slug}").status_code == 410
    filler = register_and_login(client, "deadline-filler")
    assert client.post(
        f"/surveys/share/{slug}/submit",
        headers=filler,
        json={"answers": {"q1": answer("q1", "single_choice", "a")}},
    ).status_code == 410


def test_allow_multiple_submissions_persists_each_response(api):
    client, database = api
    owner = register_and_login(client, "repeat-owner")
    survey_id, slug = create_and_publish(
        client,
        owner,
        [choice_question("q1", 1)],
        allow_multiple_submissions=True,
    )
    filler = register_and_login(client, "repeat-filler")
    payload = {"answers": {"q1": answer("q1", "single_choice", "a")}}
    first = client.post(f"/surveys/share/{slug}/submit", headers=filler, json=payload)
    second = client.post(f"/surveys/share/{slug}/submit", headers=filler, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert len([item for item in database.responses.documents if item["survey_id"] == ObjectId(survey_id)]) == 2
