import pytest

from backend.engine.approvals import ApprovalError


def test_valid_token_consumed_once(approvals):
    tok, _ = approvals.issue_token("call_1", "ORD_1024", "guard_drop_request")
    approvals.consume(tok, call_id="call_1", order_id="ORD_1024", action="guard_drop_request")
    with pytest.raises(ApprovalError) as e:
        approvals.consume(tok, call_id="call_1", order_id="ORD_1024", action="guard_drop_request")
    assert e.value.code == "reused"


@pytest.mark.parametrize("field,value,code", [
    ("call_id", "call_2", "wrong_call"),
    ("order_id", "ORD_2048", "wrong_order"),
    ("action", "change_address", "wrong_action"),
])
def test_binding_enforced(approvals, field, value, code):
    tok, _ = approvals.issue_token("call_1", "ORD_1024", "guard_drop_request")
    kw = dict(call_id="call_1", order_id="ORD_1024", action="guard_drop_request")
    kw[field] = value
    with pytest.raises(ApprovalError) as e:
        approvals.consume(tok, **kw)
    assert e.value.code == code


def test_expired_token_rejected(approvals, clock):
    tok, _ = approvals.issue_token("call_1", "ORD_1024", "guard_drop_request")
    clock.advance(31)
    with pytest.raises(ApprovalError) as e:
        approvals.consume(tok, call_id="call_1", order_id="ORD_1024", action="guard_drop_request")
    assert e.value.code == "expired"


def test_tampered_token_rejected(approvals):
    tok, _ = approvals.issue_token("call_1", "ORD_1024", "guard_drop_request")
    body, sig = tok.split(".")
    for bad in (body + "x." + sig, body + "." + sig[:-2] + "AA", "garbage", ""):
        with pytest.raises(ApprovalError):
            approvals.consume(bad, call_id="call_1", order_id="ORD_1024", action="guard_drop_request")


def test_token_from_other_secret_rejected(db, clock, approvals):
    from backend.engine.approvals import ApprovalService
    other = ApprovalService(db, "a-different-secret", clock=clock)
    tok, _ = other.issue_token("call_1", "ORD_1024", "guard_drop_request")
    with pytest.raises(ApprovalError) as e:
        approvals.consume(tok, call_id="call_1", order_id="ORD_1024", action="guard_drop_request")
    assert e.value.code == "bad_signature"


def test_unique_nonces(approvals):
    nonces = {approvals.issue_token("c", "o", "a")[1]["nonce"] for _ in range(50)}
    assert len(nonces) == 50


# ---- through the agent --------------------------------------------------

def test_approval_reuse_through_agent(agent):
    c = agent.start_call("ORD_1024")["call_id"]
    r = agent.handle_transcript(c, "Customer phone nahi utha raha. Guard ko de doon?")
    apr = agent.approvals.get(r.approval_id)
    first = agent.decide_approval(apr["id"], "approve", apr["token"])
    assert first.provider["status"] == "accepted"
    second = agent.decide_approval(apr["id"], "approve", apr["token"])
    assert second.error and second.provider is None


def test_expired_approval_falls_back_to_window_and_refuses(agent, clock, ledger):
    c = agent.start_call("ORD_1024")["call_id"]
    r = agent.handle_transcript(c, "guard ko de doon?")
    apr = agent.approvals.get(r.approval_id)
    clock.advance(31)
    out = agent.decide_approval(apr["id"], "approve", apr["token"])
    assert out.decision["action"] == "refuse"
    assert out.reply_key == "unresolved_fallback"
    assert "6 PM" in out.reply_text
    assert out.customer_message["key"] == "unresolved"
    levels = [e["evidence_level"] for e in ledger.events(call_id=c)]
    assert "provider_accepted" not in levels and "customer_approved" not in levels


def test_expire_due_sweeper(agent, clock):
    c = agent.start_call("ORD_1024")["call_id"]
    agent.handle_transcript(c, "watchman ko de du kya")
    assert agent.expire_due() == []
    clock.advance(40)
    out = agent.expire_due()
    assert len(out) == 1 and out[0].customer_message["key"] == "unresolved"
    assert agent.approvals.pending() == []


def test_forged_token_does_not_approve(agent, ledger):
    c = agent.start_call("ORD_1024")["call_id"]
    r = agent.handle_transcript(c, "guard ko de doon?")
    out = agent.decide_approval(r.approval_id, "approve", "forged.token")
    assert out.error and "token rejected" in out.error
    assert agent.approvals.get(r.approval_id)["status"] == "pending"
    assert "customer_approved" not in {e["evidence_level"] for e in ledger.events(call_id=c)}
