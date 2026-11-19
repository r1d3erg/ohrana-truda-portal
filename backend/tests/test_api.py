from factory import DEFAULT_ITEMS, build_checklist

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(client, data, name="cy1.xlsx", dry_run=False):
    return client.post(
        "/api/imports" + ("?dry_run=true" if dry_run else ""),
        files={"file": (name, data, XLSX)},
    )


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_creates_office_and_links_data(client):
    r = upload(client, build_checklist(office="cy1"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "created"
    assert body["office_created"] is True
    assert body["summary"]["readiness"] == 50.0
    assert body["office"]["code"] == "cy1"
    assert body["office"]["level"] == "bad"
    assert body["changes"]["has_previous"] is False

    offices = client.get("/api/offices").json()
    assert len(offices) == 1
    o = offices[0]
    assert o["readiness"] == 50.0 and o["check_date"] == "2026-08-17"
    assert o["counts"] == {"total": 6, "done": 3, "in_progress": 2, "missing": 1, "not_set": 0}

    card = client.get("/api/offices/cy1").json()
    assert card["current_import"]["inspector"] == "Тестов Т.Т."
    assert [c["category"] for c in card["by_category"]] == ["Охрана труда", "Первая помощь", "Пожарная безопасность"]

    dash = client.get("/api/dashboard").json()
    assert dash["offices_total"] == 1 and dash["offices_with_data"] == 1
    assert dash["avg_readiness"] == 50.0
    assert dash["documents"]["missing"] == 1


def test_checklist_filters(client):
    upload(client, build_checklist(office="cy1"))
    all_items = client.get("/api/offices/cy1/checklist").json()["items"]
    assert len(all_items) == 6
    assert all_items[0]["status_label"] == "Есть"
    missing = client.get("/api/offices/cy1/checklist", params={"status": "missing"}).json()["items"]
    assert [i["title"] for i in missing] == ["Журнал вводного инструктажа"]
    fire = client.get("/api/offices/cy1/checklist", params={"category": "Пожарная безопасность"}).json()["items"]
    assert len(fire) == 2
    found = client.get("/api/offices/cy1/checklist", params={"q": "эвакуац"}).json()["items"]
    assert len(found) == 1
    assert client.get("/api/offices/cy1/checklist", params={"status": "bad"}).status_code == 422


def test_duplicate_upload_is_not_saved_twice(client):
    data = build_checklist(office="cy1")
    upload(client, data)
    r = upload(client, data)
    assert r.json()["result"] == "duplicate"
    assert len(client.get("/api/offices/cy1/imports").json()) == 1


def test_new_check_replaces_current_and_shows_changes(client):
    upload(client, build_checklist(office="cy1", check_date="17.08.2026"))
    items = [list(i) for i in DEFAULT_ITEMS]
    items[2][4] = "Есть"        # «Нет» -> «Есть»
    items[0][4] = "В работе"    # «Есть» -> «В работе»
    r = upload(client, build_checklist(office="cy1", check_date="01.10.2026", items=[tuple(i) for i in items]))
    body = r.json()
    assert body["is_current"] is True
    ch = body["changes"]
    assert ch["improved"] == 1 and ch["worsened"] == 1
    assert {c["title"] for c in ch["changed"]} == {"Журнал вводного инструктажа", "Положение о СУОТ"}

    office = client.get("/api/offices/cy1").json()
    assert office["check_date"] == "2026-10-01"
    history = client.get("/api/offices/cy1/imports").json()
    assert [h["check_date"] for h in history] == ["2026-10-01", "2026-08-17"]
    assert history[0]["is_current"] is True and history[1]["is_current"] is False


def test_older_check_goes_to_history_only(client):
    upload(client, build_checklist(office="cy1", check_date="01.10.2026"))
    r = upload(client, build_checklist(office="cy1", check_date="01.01.2026", items=DEFAULT_ITEMS[:2]))
    body = r.json()
    assert body["is_current"] is False
    assert any("раньше" in w for w in body["warnings"])
    assert client.get("/api/offices/cy1").json()["check_date"] == "2026-10-01"


def test_dry_run_saves_nothing(client):
    r = upload(client, build_checklist(office="cy9"), dry_run=True)
    assert r.json()["result"] == "preview"
    assert r.json()["summary"]["total"] == 6
    assert client.get("/api/offices").json() == []


def test_rejects_wrong_extension(client):
    r = upload(client, b"hello", name="report.csv")
    assert r.status_code == 415


def test_rejects_invalid_file_with_errors(client):
    items = [("1. Б", None, "Охрана труда", "Док", "Готово")]
    r = upload(client, build_checklist(items=items))
    assert r.status_code == 422
    assert "неизвестный статус" in r.json()["detail"]["errors"][0]
    assert client.get("/api/offices").json() == []


def test_delete_import_restores_previous(client):
    upload(client, build_checklist(office="cy1", check_date="17.08.2026"))
    second = upload(client, build_checklist(office="cy1", check_date="01.10.2026", items=DEFAULT_ITEMS[:3])).json()
    r = client.delete(f"/api/imports/{second['import']['id']}")
    assert r.status_code == 200
    assert r.json()["office"]["check_date"] == "2026-08-17"
    assert client.get(f"/api/imports/{second['import']['id']}").status_code == 404


def test_office_create_and_assign_responsible(client):
    r = client.post("/api/offices", json={"code": "msk-1", "name": "Москва 1"})
    assert r.status_code == 201 and r.json()["level"] == "new"
    assert client.post("/api/offices", json={"code": "msk-1"}).status_code == 409
    r = client.patch("/api/offices/msk-1", json={"responsible": "Петров П.П."})
    assert r.json()["responsible"] == "Петров П.П."
    # загрузка таблицы привязывается к уже созданному офису
    up = upload(client, build_checklist(office="msk-1")).json()
    assert up["office_created"] is False
    office = client.get("/api/offices/msk-1").json()
    assert office["name"] == "Москва 1" and office["responsible"] == "Петров П.П."
    assert office["readiness"] == 50.0


def test_unknown_office_404(client):
    assert client.get("/api/offices/nope").status_code == 404
    assert client.get("/api/offices/nope/checklist").status_code == 404
