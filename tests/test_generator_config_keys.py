"""Tests for odm_map.id_generator.generator_config_keys.ConfigKeys"""

from odm_map.id_generator.generator_config_keys import ConfigKeys


class TestConfigKeys:
    def test_class_linkages_value(self):
        assert ConfigKeys.CLASS_LINKAGES == "class_linkages"

    def test_named_class_linkages_value(self):
        assert ConfigKeys.NAMED_CLASS_LINKAGES == "named_class_linkages"

    def test_tables_to_shortnames_value(self):
        assert ConfigKeys.TABLES_TO_SHORTNAMES == "tables_to_shortnames"

    def test_all_values_are_strings(self):
        assert isinstance(ConfigKeys.CLASS_LINKAGES, str)
        assert isinstance(ConfigKeys.NAMED_CLASS_LINKAGES, str)
        assert isinstance(ConfigKeys.TABLES_TO_SHORTNAMES, str)

    def test_all_values_are_distinct(self):
        values = [
            ConfigKeys.CLASS_LINKAGES,
            ConfigKeys.NAMED_CLASS_LINKAGES,
            ConfigKeys.TABLES_TO_SHORTNAMES,
        ]
        assert len(set(values)) == len(values)
