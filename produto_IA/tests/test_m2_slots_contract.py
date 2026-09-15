from src.extractors.dto_normalizer import normalize_specs_for_backend, normalize_hardware_payload_for_backend


def test_count_becomes_slots_without_invented_capabilities():
    slots = normalize_specs_for_backend("PLACA_MAE", {"slotsM2": 2})["slotsM2"]
    assert [slot["codigo"] for slot in slots] == ["M2_1", "M2_2"]
    assert all(slot["interfacesSuportadas"] == [] for slot in slots)
    assert all(slot["chavesSuportadas"] == [] for slot in slots)


def test_form_factor_is_not_slot_count():
    for value in (2280, "2280", "2 x M.2 2280", True, 2.5, -1, 17):
        assert normalize_specs_for_backend("PLACA_MAE", {"slotsM2": value})["slotsM2"] is None


def test_lists_preserved_and_never_truncated():
    slot = {"codigo": "M2_CPU", "interfacesSuportadas": ["NVME_PCIE"],
            "chavesSuportadas": ["M"], "tamanhosSuportadosMm": [80]}
    assert normalize_specs_for_backend("PLACA_MAE", {"slotsM2": [slot]})["slotsM2"] == [slot]
    assert normalize_specs_for_backend("PLACA_MAE", {"slotsM2": [slot] * 17})["slotsM2"] is None
    assert normalize_specs_for_backend("PLACA_MAE", {"slotsM2": 0})["slotsM2"] == []


def test_final_payload_normalization_is_idempotent():
    payload = {"categoria": "PLACA_MAE", "especificacaoPlacaMae": {"slotsM2": 2}}
    first = normalize_hardware_payload_for_backend("PLACA_MAE", payload)
    assert len(first["especificacaoPlacaMae"]["slotsM2"]) == 2
    assert normalize_hardware_payload_for_backend("PLACA_MAE", first) == first
