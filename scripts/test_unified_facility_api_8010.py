
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8010"


def get_json(path):
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            assert response.status == 200, (
                f"{path}: expected HTTP 200, got {response.status}"
            )
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise AssertionError(f"Request failed for {path}: {exc}") from exc


def run_test(name, check):
    try:
        check()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} — {exc}")
        return False


def test_health():
    result = get_json("/health")
    assert result["status"] == "ok"
    assert result["inventory_available"] is True
    assert result["inventory_file"].startswith(
        "unified_facility_inventory_"
    )


def test_summary():
    result = get_json("/summary")
    assert result["total_records"] == 811
    assert result["records_by_domain"]["healthcare"] == 396
    assert result["records_by_domain"]["education"] == 415
    assert result["records_with_review_flags"] == 72
    assert result["records_without_names"] == 53


def test_healthcare_filter():
    result = get_json("/facilities?domain=healthcare&limit=3")
    assert result["total"] == 396
    assert len(result["items"]) == 3
    assert all(
        item["service_domain"] == "healthcare"
        for item in result["items"]
    )


def test_education_filter():
    result = get_json("/facilities?domain=education&limit=3")
    assert result["total"] == 415
    assert len(result["items"]) == 3
    assert all(
        item["service_domain"] == "education"
        for item in result["items"]
    )


def test_review_only():
    result = get_json("/facilities?review_only=true&limit=500")
    assert result["total"] == 72
    assert all(item["review_flags"].strip() for item in result["items"])


def test_search():
    query = urllib.parse.quote("Ellen Multispeciality Hospital")
    result = get_json(f"/facilities?q={query}")
    assert result["total"] >= 1
    assert any(
        "Ellen Multispeciality Hospital" in item["facility_name"]
        for item in result["items"]
    )


def test_pagination():
    first = get_json("/facilities?domain=healthcare&limit=2&offset=0")
    second = get_json("/facilities?domain=healthcare&limit=2&offset=2")

    assert len(first["items"]) == 2
    assert len(second["items"]) == 2

    first_ids = {item["facility_uid"] for item in first["items"]}
    second_ids = {item["facility_uid"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)


def main():
    tests = [
        ("Health endpoint", test_health),
        ("Summary totals", test_summary),
        ("Healthcare filter", test_healthcare_filter),
        ("Education filter", test_education_filter),
        ("Review-only filter", test_review_only),
        ("Facility name search", test_search),
        ("Pagination", test_pagination),
    ]

    print(f"Testing AURIS-X API at {BASE_URL}\n")
    results = [run_test(name, check) for name, check in tests]

    passed = sum(results)
    failed = len(results) - passed

    print(f"\nResults: {passed} passed, {failed} failed out of {len(results)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
