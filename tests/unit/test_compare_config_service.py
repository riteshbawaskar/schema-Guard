from app.services.xml_mapping_service import load_mapping, save_mapping


def test_xml_specific_mappings_are_saved_and_reloaded(tmp_path):
    path = tmp_path / "compare.yaml"
    config = {
        "attribute_mappings": [],
        "ignored_attributes": ["length"],
        "xml": {
            "attribute_mappings": [
                {"source": "type", "target": "datatype", "enabled": False, "compare": True},
                {"source": "displayFormat", "target": "display_format", "enabled": True, "compare": False},
            ]
        },
    }
    save_mapping(config, path)
    loaded = load_mapping(path)
    assert loaded["xml"]["attribute_mappings"][0]["enabled"] is False
    assert loaded["xml"]["attribute_mappings"][1]["compare"] is False
    assert loaded["ignored_attributes"] == ["length"]
