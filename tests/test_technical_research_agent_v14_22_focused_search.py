from src.research_agent.focused_search import FocusedSearchResolver
from src.research_agent.query_builder import build_focus_terms, build_focused_queries


def test_motherboard_gaps_generate_specific_technical_terms():
    terms = build_focus_terms(
        "PLACA_MAE",
        ["biosFlashback", "ethernet", "slotsM2", "capacidadeMaximaPorSlotGb"],
    )

    assert "BIOS Flashback" in terms
    assert "LAN ethernet controller" in terms
    assert "M.2 slots" in terms
    assert "maximum memory per slot" in terms


def test_focused_query_keeps_hardware_identity_and_adds_gap_terms():
    queries = build_focused_queries(
        "MSI B550-A Pro",
        "PLACA_MAE",
        ["biosFlashback", "ethernet", "slotsM2"],
    )

    assert queries[0].startswith("MSI B550-A Pro")
    assert "BIOS Flashback" in queries[0]
    assert "LAN ethernet controller" in queries[0]
    assert queries[-1] == "MSI B550-A Pro"


def test_resolver_tries_focused_query_before_generic_query():
    class FakeDelegate:
        allow_browser_fallback = False
        timeout = 5
        last_status = "NAO_ENCONTRADO"

        def __init__(self):
            self.calls = []

        def first_result(self, query, allowed_domains):
            self.calls.append((query, tuple(allowed_domains)))
            if "BIOS Flashback" in query:
                self.last_status = "ENCONTRADO"
                return "https://www.msi.com/Motherboard/B550-A-PRO/support"
            return None

        def results(self, query, allowed_domains, limit=10):
            self.calls.append((query, tuple(allowed_domains)))
            return []

    delegate = FakeDelegate()
    resolver = FocusedSearchResolver(
        delegate,
        category="PLACA_MAE",
        missing_fields=["biosFlashback", "ethernet", "slotsM2"],
    )

    found = resolver.first_result("MSI B550-A Pro", ["msi.com"])

    assert found.endswith("/support")
    assert "BIOS Flashback" in delegate.calls[0][0]
    assert delegate.calls[0][0] != "MSI B550-A Pro"
    assert resolver.queries_executed == [delegate.calls[0][0]]


def test_resolver_falls_back_to_generic_query_when_focused_search_finds_nothing():
    class FakeDelegate:
        allow_browser_fallback = False
        timeout = 5
        last_status = "NAO_ENCONTRADO"

        def __init__(self):
            self.queries = []

        def first_result(self, query, _allowed_domains):
            self.queries.append(query)
            if query == "MSI B550-A Pro":
                return "https://www.msi.com/Motherboard/B550-A-PRO"
            return None

        def results(self, *_args, **_kwargs):
            return []

    delegate = FakeDelegate()
    resolver = FocusedSearchResolver(
        delegate,
        category="PLACA_MAE",
        missing_fields=["biosFlashback"],
    )

    found = resolver.first_result("MSI B550-A Pro", ["msi.com"])

    assert found.endswith("B550-A-PRO")
    assert len(delegate.queries) == 2
    assert "BIOS Flashback" in delegate.queries[0]
    assert delegate.queries[1] == "MSI B550-A Pro"
