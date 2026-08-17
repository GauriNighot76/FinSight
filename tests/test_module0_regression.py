from database import queries


def test_existing_module0_core_workflow():
    user_id = queries.create_user("test@example.com", "9876543210", "legacy-hash",
                                  "Question", "answer-hash")
    business_id = queries.create_business(user_id, "Test Business", "Retail", "Pune")
    entity_id = queries.create_counterparty(business_id, "Supplier", "supplier")
    transaction = queries.create_transaction(
        business_id, entity_id, user_id, "2026-08-01", 1500, "expense",
        "Office Supplies", "UPI", "Supplies",
    )
    queries.create_budget(business_id, "Office Supplies", 5000, user_id)
    summary = queries.get_financial_summary(business_id, user_id)
    variance = queries.get_budget_variance(business_id, user_id)
    document_id = queries.create_document(user_id, "test.pdf", "application/pdf", "data/test.pdf")
    queries.create_document_chunk(document_id, user_id, 0, "Test chunk")

    assert transaction["duplicate"] is False
    assert len(queries.get_business_transactions(business_id, user_id)) == 1
    assert summary["net_cash_flow"] == -1500.0
    assert variance[0]["variance"] == 3500.0
    assert len(queries.get_document_chunks(document_id, user_id)) == 1
