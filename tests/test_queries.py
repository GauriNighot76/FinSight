from database import queries


def test_database():
    print("\nStarting database tests...\n")

    # ---------------------------------------------------------
    # 1. Create user
    # ---------------------------------------------------------

    user_id = queries.create_user(
        email="test@example.com",
        contact_number="9876543210",
        password_hash="hashed_password",
        secret_question="What is your pet name?",
        secret_answer_hash="hashed_answer",
    )

    assert user_id is not None

    print("PASS: User created")
    print("User ID:", user_id)

    # ---------------------------------------------------------
    # 2. Get user
    # ---------------------------------------------------------

    user = queries.get_user_by_email(
        "test@example.com"
    )

    assert user is not None
    assert user["email"] == "test@example.com"

    print("PASS: User retrieved")
    print("Email:", user["email"])

    # ---------------------------------------------------------
    # 3. Create business
    # ---------------------------------------------------------

    business_id = queries.create_business(
        user_id=user_id,
        business_name="Test Business",
        business_type="Retail",
        address="Pune, Maharashtra",
    )

    assert business_id is not None

    print("PASS: Business created")
    print("Business ID:", business_id)

    # ---------------------------------------------------------
    # 4. Get business
    # ---------------------------------------------------------

    business = queries.get_business_by_id(
        business_id=business_id,
        user_id=user_id,
    )

    assert business is not None
    assert business["business_name"] == "Test Business"

    print("PASS: Business retrieved")
    print("Business Name:", business["business_name"])

    # ---------------------------------------------------------
    # 5. Create counterparty
    # ---------------------------------------------------------

    entity_id = queries.create_counterparty(
        business_id=business_id,
        entity_name="Test Supplier",
        entity_type="supplier",
    )

    assert entity_id is not None

    print("PASS: Counterparty created")
    print("Entity ID:", entity_id)

    # ---------------------------------------------------------
    # 6. Create transaction
    # ---------------------------------------------------------

    transaction = queries.create_transaction(
        business_id=business_id,
        entity_id=entity_id,
        user_id=user_id,
        transaction_date="2026-08-01",
        amount=1500.00,
        transaction_type="expense",
        category="Office Supplies",
        payment_mode="UPI",
        description="Purchased office supplies",
    )

    assert transaction is not None
    assert transaction["transaction_id"] is not None

    print("PASS: Transaction created")
    print("Transaction ID:", transaction["transaction_id"])

    # ---------------------------------------------------------
    # 7. Get transactions
    # ---------------------------------------------------------

    transactions = queries.get_business_transactions(
        business_id=business_id,
        user_id=user_id,
    )

    assert len(transactions) == 1

    print("PASS: Transactions retrieved")
    print("Transaction count:", len(transactions))

    # ---------------------------------------------------------
    # 8. Financial summary
    # ---------------------------------------------------------

    summary = queries.get_financial_summary(
        business_id=business_id,
        user_id=user_id,
    )

    assert summary is not None
    assert summary["total_transactions"] == 1
    assert summary["total_income"] == 0.0
    assert summary["total_expense"] == 1500.0
    assert summary["net_cash_flow"] == -1500.0

    print("PASS: Financial summary retrieved")
    print("Summary:", summary)

    # ---------------------------------------------------------
    # 9. Create budget
    # ---------------------------------------------------------

    budget_id = queries.create_budget(
        business_id=business_id,
        category="Office Supplies",
        allocated_amount=5000.00,
        user_id=user_id,
    )

    assert budget_id is not None

    print("PASS: Budget created")
    print("Budget ID:", budget_id)

    # ---------------------------------------------------------
    # 10. Get budgets
    # ---------------------------------------------------------

    budgets = queries.get_business_budgets(
        business_id=business_id,
        user_id=user_id,
    )

    assert len(budgets) == 1
    assert budgets[0]["category"] == "Office Supplies"

    print("PASS: Budgets retrieved")
    print("Budget count:", len(budgets))

    # ---------------------------------------------------------
    # 11. Get budget variance
    # ---------------------------------------------------------

    variance = queries.get_budget_variance(
        business_id=business_id,
        user_id=user_id,
    )

    assert len(variance) == 1

    print("PASS: Budget variance retrieved")
    print("Variance:", dict(variance[0]))

    # ---------------------------------------------------------
    # 12. Test document creation
    # ---------------------------------------------------------

    document_id = queries.create_document(
        user_id=user_id,
        file_name="test_document.pdf",
        file_type="application/pdf",
        file_path="data/test_document.pdf",
    )

    assert document_id is not None

    print("PASS: Document created")
    print("Document ID:", document_id)

    # ---------------------------------------------------------
    # 13. Get user documents
    # ---------------------------------------------------------

    documents = queries.get_user_documents(
        user_id=user_id,
    )

    assert len(documents) == 1
    assert documents[0]["file_name"] == "test_document.pdf"

    print("PASS: Documents retrieved")
    print("Document count:", len(documents))

    # ---------------------------------------------------------
    # 14. Create document chunk
    # ---------------------------------------------------------

    chunk_id = queries.create_document_chunk(
        document_id=document_id,
        user_id=user_id,
        chunk_index=0,
        chunk_text="This is a test document chunk.",
    )

    assert chunk_id is not None

    print("PASS: Document chunk created")
    print("Chunk ID:", chunk_id)

    # ---------------------------------------------------------
    # 15. Get document chunks
    # ---------------------------------------------------------

    chunks = queries.get_document_chunks(
        document_id=document_id,
        user_id=user_id,
    )

    assert len(chunks) == 1
    assert chunks[0]["chunk_text"] == "This is a test document chunk."

    print("PASS: Document chunks retrieved")
    print("Chunk count:", len(chunks))

    # ---------------------------------------------------------
    # FINAL
    # ---------------------------------------------------------

    print("\nAll database query tests completed successfully.\n")