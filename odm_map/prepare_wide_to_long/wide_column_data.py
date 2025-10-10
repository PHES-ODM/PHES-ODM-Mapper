class ConfigKeys:
    TABLES_TO_SHORTNAMES = "tables_to_shortnames"
    PARTID_TO_MMASET = "partid_to_mmaset"
    SEE_HEADERS = "see_headers"


class WideColumnValues:
    COLUMN_PART_SEPARATOR = "_"
    COLUMN_MEASURE_TAG = "mes"
    COLUMN_METHOD_TAG = "met"
    COLUMN_PROTOCOL_STEPS_TAG = "ps"
    AND_TAG = "AND"
    OR_TAG = "OR"
    NR_TAG = "NR"
    VALUE_TAG = "value"


class MeasureTableColumns:
    COMPARTMENT = "mr_compartment"
    SPECIMEN = "mr_specimen"
    FRACTION = "mr_fraction"
    MEASURE = "mr_measure"
    UNIT = "mr_unit"
    AGGREGATION = "mr_aggregation"
    INDEX = "mr_index"
    VALUE = "mr_value"


class ProtocolStepsTableColumns:
    METHOD = "ps_method"
    MEASURE = "ps_measure"
    VALUE = "ps_value"
    UNIT = "ps_unit"
    AGGREGATION = "ps_aggregation"
    INDEX = "ps_index"


AND_VALUE_SEPARATOR = "."
COLUMN_INDEX_SEPARATOR = ":"
