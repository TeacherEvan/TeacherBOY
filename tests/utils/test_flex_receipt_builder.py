"""Tests for Flex receipt bubble builder."""

from src.utils.flex_receipt_builder import build_receipt_bubble


def test_build_receipt_bubble_all_fields():
    """Full result dict should produce a bubble with all components."""
    result = {
        "source": "app-camera",
        "fields": {
            "merchant": {"value": "Test Cafe"},
            "total": {"value": 42.50},
            "category": {"value": "food"},
            "currency": {"value": "USD"},
        },
        "confidence": {"total": 0.85},
        "draftId": "draft_123",
    }

    bubble = build_receipt_bubble(result, app_url="https://budgetboss.app")

    assert bubble is not None
    # Header contains "Receipt Scanned"
    header_text = bubble.header.contents[0].text
    assert "Receipt Scanned" in header_text
    # Body has merchant, total, category, separator, confidence
    assert len(bubble.body.contents) == 5
    # Footer has deep link button
    assert len(bubble.footer.contents) == 1
    assert bubble.footer.contents[0].action.uri == "https://budgetboss.app/receipts/draft_123"


def test_build_receipt_bubble_defaults():
    """Missing fields should use safe defaults."""
    result = {}

    bubble = build_receipt_bubble(result)

    # Should not crash
    assert bubble is not None
    assert bubble.header is not None
    assert bubble.body is not None
    assert bubble.footer is not None


def test_build_receipt_bubble_thb_currency():
    """Thai Baht should use the ฿ symbol."""
    result = {
        "fields": {
            "merchant": {"value": "ร้านกาแฟ"},
            "total": {"value": 250},
            "category": {"value": "food"},
            "currency": {"value": "THB"},
        },
        "confidence": {"total": 0.75},
        "draftId": "draft_th",
    }

    bubble = build_receipt_bubble(result)
    body_texts = []
    for box in bubble.body.contents:
        if hasattr(box, "contents") and box.contents:
            for c in box.contents:
                if hasattr(c, "text"):
                    body_texts.append(c.text)
    # Total text should contain ฿
    total_text = [t for t in body_texts if "฿" in t]
    assert len(total_text) == 1
    assert "250.00" in total_text[0]


def test_build_receipt_bubble_unknown_currency():
    """Unknown currency code should fall back to the code itself."""
    result = {
        "fields": {
            "merchant": {"value": "Shop"},
            "total": {"value": 100},
            "category": {"value": "other"},
            "currency": {"value": "XYZ"},
        },
        "confidence": {"total": 0.6},
        "draftId": "draft_xyz",
    }

    bubble = build_receipt_bubble(result)
    # Find total text in body
    found = False
    for box in bubble.body.contents:
        if hasattr(box, "contents") and box.contents:
            for item in box.contents:
                if hasattr(item, "text") and "XYZ" in item.text:
                    assert "100.00" in item.text
                    found = True
    assert found, "Total with XYZ currency not found"
