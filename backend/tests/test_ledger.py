import sqlite3

import pytest

from backend.engine.ledger import GENESIS, Ledger


def _fill(ledger, n=5):
    for i in range(n):
        ledger.append(order_id="ORD_1024", call_id="c1", event_type=f"e{i}", evidence_level="info",
                      source="test", detail={"i": i})


def test_chain_links_and_verifies(ledger):
    _fill(ledger)
    ev = ledger.events()
    assert ev[0]["prev_hash"] == GENESIS
    assert all(ev[i]["prev_hash"] == ev[i - 1]["hash"] for i in range(1, len(ev)))
    rep = ledger.verify_chain()
    assert rep.ok and rep.checked == 5


def test_every_event_is_simulated(ledger):
    _fill(ledger, 3)
    assert all(e["simulated"] is True for e in ledger.events())


def test_update_and_delete_blocked_by_db(db, ledger):
    _fill(ledger, 2)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE ledger SET evidence_level='provider_accepted' WHERE seq=1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM ledger WHERE seq=1")


def test_tamper_detected_even_if_triggers_dropped(db, ledger):
    _fill(ledger, 4)
    db.execute("DROP TRIGGER ledger_no_update")  # attacker with raw DB access
    db.execute("UPDATE ledger SET detail_json='{\"i\":99}' WHERE seq=2")
    rep = ledger.verify_chain()
    assert not rep.ok and rep.broken_at == 2 and "edited" in rep.reason


def test_evidence_upgrade_tamper_detected(db, ledger):
    _fill(ledger, 3)
    db.execute("DROP TRIGGER ledger_no_update")
    db.execute("UPDATE ledger SET evidence_level='provider_accepted' WHERE seq=3")
    assert not ledger.verify_chain().ok


def test_deleted_row_detected(db, ledger):
    _fill(ledger, 4)
    db.execute("DROP TRIGGER ledger_no_delete")
    db.execute("DELETE FROM ledger WHERE seq=2")
    rep = ledger.verify_chain()
    assert not rep.ok and rep.reason == "prev_hash mismatch"


def test_unknown_evidence_level_rejected(ledger):
    with pytest.raises(ValueError):
        ledger.append(order_id="o", call_id="c", event_type="x", evidence_level="delivered", source="t")


def test_highest_evidence():
    ev = [{"evidence_level": "requested"}, {"evidence_level": "customer_approved"}, {"evidence_level": "info"}]
    assert Ledger.highest_evidence(ev) == "customer_approved"


def test_full_call_chain_verifies(agent, ledger):
    c = agent.start_call("ORD_1024")["call_id"]
    r = agent.handle_transcript(c, "guard ko de doon?")
    apr = agent.approvals.get(r.approval_id)
    agent.decide_approval(apr["id"], "approve", apr["token"])
    assert ledger.verify_chain().ok
