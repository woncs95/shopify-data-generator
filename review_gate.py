import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STATUSES = ("Abgelehnt", "Review", "Freigegeben")

PRODUCT_COUNTERFEIT_PATTERNS = {
    "fälschung": "Fälschungsvorwurf",
    "gefälscht": "Fälschungsvorwurf",
    "nicht echt": "Fälschungsvorwurf",
    "nachgemacht": "Fälschungsvorwurf",
    "fake": "Fälschungsvorwurf",
}

EASYCOSMETIC_ACCUSATION_PATTERNS = {
    "betrug": "Vorwurf gegen easycosmetic",
    "abzocke": "Vorwurf gegen easycosmetic",
    "geld aus der tasche": "Vorwurf gegen easycosmetic",
}

SERVICE_ISSUE_PATTERNS = {
    "lieferung": "Service-Mangel",
    "geliefert": "Service-Mangel",
    "versand": "Service-Mangel",
    "paket": "Service-Mangel",
    "verpackung": "Service-Mangel",
    "bestellung": "Service-Mangel",
    "kundenservice": "Service-Mangel",
    "kundendienst": "Service-Mangel",
}

LOW_VALUE_COMMENTS = {
    "ok",
    "okay",
    "top",
    "gut",
    "super",
}

UNCLEAR_REVIEW_PATTERNS = {
    "bin mir noch unsicher",
    "noch unsicher",
    "nicht sicher",
    "kann ich noch nicht sagen",
    "erst seit",
}

FORMAL_CORRECTIONS = (
    (re.compile(r"\bNr\.\s*(\d+)"), r"Nr. \1"),
    (re.compile(r"\b(\d+)\s*(ml|g|kg|l|cm|mm)\b", re.IGNORECASE), r"\1 \2"),
    (re.compile(r"\bmake[\s-]?up\b", re.IGNORECASE), "Make-up"),
    (re.compile(r"\beasy\s*cosmetic\b", re.IGNORECASE), "easycosmetic"),
    (re.compile(r"\bVitamin\s+C\b", re.IGNORECASE), "Vitamin-C"),
)


def normalize_comment(review):
    comment = review.get("comment")
    if comment is None:
        return ""
    return str(comment).strip()


def formal_correct_comment(comment):
    corrected = str(comment or "").strip()
    corrected = re.sub(r"\s+", " ", corrected)
    corrected = re.sub(r"\s+([,.!?;:])", r"\1", corrected)

    for pattern, replacement in FORMAL_CORRECTIONS:
        corrected = pattern.sub(replacement, corrected)

    return corrected


def contains_pattern(text, patterns):
    for pattern, reason in patterns.items():
        if pattern in text:
            return reason
    return None


def is_low_value_comment(comment):
    text = comment.lower().strip()
    if not text:
        return True
    if text in LOW_VALUE_COMMENTS:
        return True
    return re.search(r"[0-9A-Za-zÄÖÜäöüß]", text) is None


def rejection_reason(review):
    comment = normalize_comment(review)
    text = comment.lower()

    if is_low_value_comment(comment):
        return "Kein SEO-/AEO-Nutzen"

    for patterns in (
        PRODUCT_COUNTERFEIT_PATTERNS,
        EASYCOSMETIC_ACCUSATION_PATTERNS,
        SERVICE_ISSUE_PATTERNS,
    ):
        reason = contains_pattern(text, patterns)
        if reason:
            return reason

    return None


def review_reason(review):
    lang = (review.get("lang") or "").lower()
    text = normalize_comment(review).lower()

    if lang and lang != "de":
        return "Fremdsprache - manuelle Nachbearbeitung"

    if contains_pattern(text, {pattern: "Unklare Entscheidungsgrundlage - manuelle Nachbearbeitung" for pattern in UNCLEAR_REVIEW_PATTERNS}):
        return "Unklare Entscheidungsgrundlage - manuelle Nachbearbeitung"

    return None


def classify(review):
    reason = rejection_reason(review)
    if reason:
        return {"status": "Abgelehnt", "reason": reason}

    reason = review_reason(review)
    if reason:
        return {"status": "Review", "reason": reason}

    return {
        "status": "Freigegeben",
        "reason": None,
        "corrected_comment": formal_correct_comment(normalize_comment(review)),
    }


def run(reviews):
    return {r["id"]: classify(r) for r in reviews}


def summarize(results):
    return {
        "status_counts": {
            status: sum(1 for result in results.values() if result["status"] == status)
            for status in STATUSES
        },
        "review_ids": [
            review_id
            for review_id, result in results.items()
            if result["status"] == "Review"
        ],
    }


def run_report(reviews):
    results = run(reviews)
    return {
        "results": results,
        "summary": summarize(results),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "reviews.json"
    with open(path, encoding="utf-8") as f:
        reviews = json.load(f)
    print(json.dumps(run_report(reviews), indent=2, ensure_ascii=False))
