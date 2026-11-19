from datetime import date, timedelta

import pytest

from app.registers import ValidationFailed, add_months, add_years, prepare_opr, prepare_sout

TODAY = date.today()


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


# --- расчёты без БД -----------------------------------------------------------
def test_add_months_and_years_handle_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_years(date(2024, 2, 29), 5) == date(2029, 2, 28)


def test_sout_valid_until_is_5_years_from_fgis_date():
    p = prepare_sout({"report_date": date(2024, 3, 1), "fgis_date": date(2024, 3, 10)})
    assert p["valid_until"] == date(2029, 3, 10)
    p = prepare_sout({"report_date": date(2024, 3, 1)})  # без ФГИС — от отчёта
    assert p["valid_until"] == date(2029, 3, 1)


def test_unplanned_due_date_12_or_6_months():
    p = prepare_sout({"kind": "unplanned", "status": "planned", "reason": "new_workplaces", "reason_date": date(2026, 1, 15)})
    assert p["due_date"] == date(2027, 1, 15)
    p = prepare_sout({"kind": "unplanned", "status": "planned", "reason": "git_order", "reason_date": date(2026, 1, 15)})
    assert p["due_date"] == date(2026, 7, 15)
    # п. 3 ч. 1 ст. 17 (изменение техпроцесса) — 12 месяцев, п. 4 (материалы) — 6
    p = prepare_sout({"kind": "unplanned", "status": "planned", "reason": "process_change", "reason_date": date(2026, 1, 15)})
    assert p["due_date"] == date(2027, 1, 15)
    p = prepare_sout({"kind": "unplanned", "status": "planned", "reason": "materials_change", "reason_date": date(2026, 1, 15)})
    assert p["due_date"] == date(2026, 7, 15)


@pytest.mark.parametrize("data, text", [
    ({"status": "completed"}, "дату утверждения отчёта"),
    ({"kind": "unplanned", "status": "planned"}, "основание"),
    ({"report_date": date(2026, 1, 1), "workplaces_total": 5, "workplaces_assessed": 6}, "больше, чем всего"),
    ({"report_date": date(2026, 1, 1), "workplaces_assessed": 3, "class_2": 4}, "Сумма по классам"),
    ({"report_date": date(2026, 1, 1), "fgis_date": date(2025, 12, 1)}, "ФГИС раньше"),
    ({"report_date": date(2026, 1, 1), "kind": "weird"}, "недопустимое"),
])
def test_sout_validation(data, text):
    with pytest.raises(ValidationFailed) as e:
        prepare_sout(data)
    assert any(text in err for err in e.value.errors)


def test_opr_default_review_and_validation():
    p = prepare_opr({"assessment_date": date(2026, 3, 1)})
    assert p["next_review_date"] == date(2027, 3, 1)
    with pytest.raises(ValidationFailed):
        prepare_opr({"assessment_date": date(2026, 3, 1), "next_review_date": date(2026, 2, 1)})
    with pytest.raises(ValidationFailed):
        prepare_opr({"assessment_date": date(2026, 3, 1), "measures_planned": 2, "measures_done": 3})


# --- API ----------------------------------------------------------------------
def make_office(client, code="cy1"):
    assert client.post("/api/offices", json={"code": code}).status_code == 201


def test_sout_crud_and_state(client):
    make_office(client)
    r = client.post("/api/offices/cy1/sout", json={
        "report_date": d(-100), "fgis_date": d(-95), "contractor": "ООО «Оценка»",
        "workplaces_total": 10, "workplaces_assessed": 10, "analogous_workplaces": 6,
        "class_2": 10, "familiarized_date": d(-90), "published_date": d(-90),
    })
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["valid_until"] == add_years(TODAY - timedelta(days=95), 5).isoformat()
    assert rec["coverage"] == 100.0 and rec["harmful_workplaces"] == 0

    state = client.get("/api/offices/cy1/sout").json()
    assert state["state"] == "ok" and state["level"] == "good" and state["alerts"] == []
    assert len(state["records"]) == 1

    # изменение: вредные условия на 2 местах -> предупреждение
    body = {**{k: rec[k] for k in ("report_date", "fgis_date", "workplaces_total", "workplaces_assessed",
                                    "familiarized_date", "published_date")}, "class_2": 8, "class_3_1": 2}
    assert client.put(f"/api/sout/{rec['id']}", json=body).status_code == 200
    state = client.get("/api/offices/cy1/sout").json()
    assert any("вредными" in a["text"] for a in state["alerts"])

    assert client.delete(f"/api/sout/{rec['id']}").status_code == 200
    assert client.get("/api/offices/cy1/sout").json()["state"] == "none"


def test_sout_expiring_expired_and_familiarization(client):
    make_office(client, "a1")
    make_office(client, "b2")
    # a1: истекает через 60 дней
    client.post("/api/offices/a1/sout", json={"report_date": d(-1700), "valid_until": d(60),
                                              "familiarized_date": d(-1690)})
    # b2: срок истёк; отдельно — свежая СОУТ без ознакомления
    client.post("/api/offices/b2/sout", json={"report_date": d(-40), "valid_until": d(-1)})
    states = {s["office_code"]: s for s in client.get("/api/sout").json()}
    assert states["a1"]["state"] == "expiring" and states["a1"]["level"] == "warn"
    assert states["b2"]["state"] == "expired" and states["b2"]["level"] == "bad"
    assert any("ознакомление" in a["text"] for a in states["b2"]["alerts"])


def test_sout_declaration_and_unplanned(client):
    make_office(client)
    client.post("/api/offices/cy1/sout", json={
        "report_date": d(-2000), "valid_until": d(-200), "class_1": 3, "class_2": 5,
        "declaration_submitted": True, "familiarized_date": d(-1990),
    })
    s = client.get("/api/offices/cy1/sout").json()
    assert s["state"] == "declared" and s["level"] == "good"  # повторная СОУТ не нужна

    client.post("/api/offices/cy1/sout", json={
        "kind": "unplanned", "status": "planned", "reason": "new_workplaces", "reason_date": d(-400),
    })
    s = client.get("/api/offices/cy1/sout").json()
    assert s["pending"][0]["due_overdue"] is True
    assert s["level"] == "bad" and any("Просрочена внеплановая" in a["text"] for a in s["alerts"])


def test_opr_state_and_alerts(client):
    make_office(client)
    r = client.post("/api/offices/cy1/opr", json={
        "assessment_date": d(-320), "method": "matrix", "hazards_identified": 14,
        "risks_low": 10, "risks_medium": 3, "risks_high": 1, "measures_planned": 4, "measures_done": 1,
    })
    assert r.status_code == 201, r.text
    assert r.json()["next_review_date"] == add_months(TODAY - timedelta(days=320), 12).isoformat()
    s = client.get("/api/offices/cy1/opr").json()
    assert s["state"] == "review_soon"
    texts = " | ".join(a["text"] for a in s["alerts"])
    assert "не утверждён план" in texts and "Высоких рисков: 1" in texts and "не ознакомлены" in texts
    assert s["level"] == "bad"  # высокий риск с невыполненными мероприятиями

    client.post("/api/offices/cy1/opr", json={"assessment_date": d(-800), "next_review_date": d(-10)})
    # актуальная — более свежая (d(-320)), старая на состояние не влияет
    assert client.get("/api/offices/cy1/opr").json()["state"] == "review_soon"


def test_validation_and_404(client):
    make_office(client)
    r = client.post("/api/offices/cy1/sout", json={"status": "completed"})
    assert r.status_code == 422 and "дату утверждения" in r.json()["detail"]["errors"][0]
    assert client.post("/api/offices/cy1/sout", json={"report_date": d(-1), "class_2": -1}).status_code == 422
    assert client.post("/api/offices/nope/sout", json={"report_date": d(-1)}).status_code == 404
    assert client.put("/api/opr/999", json={"assessment_date": d(-1)}).status_code == 404


def test_dashboard_registers_block(client):
    make_office(client, "a1")
    make_office(client, "b2")
    client.post("/api/offices/a1/sout", json={"report_date": d(-40), "valid_until": d(-1)})
    client.post("/api/offices/a1/opr", json={"assessment_date": d(-30), "risks_high": 2,
                                             "plan_approved_date": d(-20), "employees_informed_date": d(-20)})
    reg = client.get("/api/dashboard").json()["registers"]
    assert reg["sout"]["counts"]["expired"] == 1 and reg["sout"]["counts"]["none"] == 1
    assert reg["opr"]["high_risks"] == 2
    assert reg["sout"]["by_office"]["a1"]["state"] == "expired"
    assert reg["alerts"][0]["severity"] == "bad"
    assert reg["alerts_bad"] >= 2

    cfg = client.get("/api/config").json()
    assert cfg["sout_reasons"]["new_workplaces"]["months"] == 12
