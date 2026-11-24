from datetime import date, timedelta
from urllib.parse import quote

import pytest

from app.directions import evaluate, prepare
from app.models import Office
from app.registers import ValidationFailed, add_months

TODAY = date.today()


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def months_ago(n: int, extra_days: int = 0) -> str:
    return (add_months(TODAY, -n) - timedelta(days=extra_days)).isoformat()


OFFICE = Office(id=1, code="t1", name="t1")

GOOD_FIRE = {
    "responsible": "Иванов И.И.", "responsible_training_date": d(-100), "people_50plus": False,
    "duties_split": "landlord", "instruction_approved": True, "evac_plan": True,
    "extinguishers_count": 4, "extinguishers_recharge_due": d(300), "extinguishers_inspection_date": d(-10),
    "briefing_repeat_date": d(-100), "drill_date": d(-60),
}


# --- без БД --------------------------------------------------------------------
def test_no_data_is_none_state():
    st = evaluate("fire", OFFICE, None)
    assert st["state"] == "none" and st["level"] == "new"


def test_complete_fire_card_is_ok():
    st = evaluate("fire", OFFICE, prepare("fire", GOOD_FIRE))
    assert st["state"] == "ok", st["alerts"]
    assert st["next_due"]["label"]


def test_fire_briefing_every_6_months_when_50_plus():
    data = prepare("fire", {**GOOD_FIRE, "briefing_repeat_date": months_ago(7)})
    # 7 месяцев < 12 — без 50+ человек инструктаж не просрочен
    assert not any("противопожарный" in a["text"] and a["severity"] == "bad"
                   for a in evaluate("fire", OFFICE, data)["alerts"])
    data50 = prepare("fire", {**GOOD_FIRE, "people_50plus": True, "briefing_repeat_date": months_ago(7)})
    st = evaluate("fire", OFFICE, data50)
    assert st["state"] == "overdue"
    assert any("противопожарный инструктаж" in a["text"] for a in st["alerts"])


def test_extinguisher_recharge_overdue_and_soon():
    st = evaluate("fire", OFFICE, prepare("fire", {**GOOD_FIRE, "extinguishers_recharge_due": d(-1)}))
    assert st["state"] == "overdue"
    st = evaluate("fire", OFFICE, prepare("fire", {**GOOD_FIRE, "extinguishers_recharge_due": d(10)}))
    assert st["state"] == "soon"


def test_electro_rules_depend_on_network_owner():
    base = {"network_owner": "landlord", "assigner": "Петров", "assigner_group": "III", "program_approved": True,
            "group1_date": d(-30), "walkthrough_date": d(-2)}
    assert evaluate("electro", OFFICE, prepare("electro", base))["state"] == "ok"
    st = evaluate("electro", OFFICE, prepare("electro", {**base, "network_owner": "company"}))
    assert st["state"] == "overdue"
    assert any("ответственный за электрохозяйство" in a["text"] for a in st["alerts"])
    st = evaluate("electro", OFFICE, prepare("electro", {**base, "assigner_group": "II"}))
    assert any("ниже III" in a["text"] for a in st["alerts"])
    st = evaluate("electro", OFFICE, prepare("electro", {**base, "group1_overdue": 3}))
    assert st["state"] == "overdue"


def test_go_plan_required_only_for_categorized():
    base = {"authorized": "Сидоров", "authorized_training_date": d(-200), "head_training_date": d(-200),
            "program_approved": True, "es_briefing_date": d(-30), "exercise_date": d(-30), "memo_posted": True}
    assert evaluate("go", OFFICE, prepare("go", base))["state"] == "ok"
    st = evaluate("go", OFFICE, prepare("go", {**base, "go_category": True}))
    assert any("план ГО" in a["text"] for a in st["alerts"])


@pytest.mark.parametrize("data, text", [
    ({"extinguishers_count": -1}, "Огнетушителей"),
    ({"duties_split": "nobody"}, "недопустимое значение"),
    ({"drill_date": "31.12.2026"}, "ожидается дата"),
    ({"drill_date": "2999-01-01"}, "дата в будущем"),
])
def test_prepare_validation(data, text):
    with pytest.raises(ValidationFailed) as e:
        prepare("fire", data)
    assert any(text in x for x in e.value.errors)


def test_unknown_fields_dropped():
    assert "hack" not in prepare("go", {"hack": 1})


# --- API -------------------------------------------------------------------------
def test_api_roundtrip_and_dashboard(client):
    assert client.post("/api/offices", json={"code": "RU 1"}).status_code == 201
    code = quote("RU 1", safe="")
    spec = client.get("/api/directions/fire/spec").json()
    assert spec["title"] == "Пожарная безопасность" and spec["fields"]

    assert client.get(f"/api/offices/{code}/directions/fire").json()["state"] == "none"
    r = client.put(f"/api/offices/{code}/directions/fire", json=GOOD_FIRE)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "ok"
    assert r.json()["data"]["responsible"] == "Иванов И.И."

    bad = client.put(f"/api/offices/{code}/directions/fire", json={"extinguishers_count": "abc"})
    assert bad.status_code == 422

    summary = client.get("/api/directions/fire").json()
    assert summary[0]["office_code"] == "RU 1" and summary[0]["state"] == "ok"

    dash = client.get("/api/dashboard").json()
    dirs = dash["registers"]["directions"]
    assert set(dirs) == {"fire", "electro", "go"}
    assert dirs["fire"]["by_office"]["RU 1"]["state"] == "ok"
    assert dirs["electro"]["by_office"]["RU 1"]["state"] == "none"
    assert any(a["kind"] == "go" for a in dash["registers"]["alerts"])

    assert client.get("/api/directions/nope").status_code == 404
    assert client.get("/api/offices/nope/directions/fire").status_code == 404
    # карточка офиса по-прежнему открывается (маршрут {code:path} не перехвачен)
    assert client.get(f"/api/offices/{code}").json()["code"] == "RU 1"
