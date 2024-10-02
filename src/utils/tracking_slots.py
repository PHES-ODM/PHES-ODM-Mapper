# All tracking slots. These slots are added to the data to map before mapping occurs.
# Slot derivations are also added to all LinkML-Map schemas to copy these tracking slots to
# the output data. This allows us to determine which source class, source row, and source file
# that the output rows were populated from.
class TrackingSlots:
    SOURCE_CLASS = "(__source_class__)"
    SOURCE_ROW = "(__source_row__)"
    SOURCE_FILE = "(__source_file__)"
    SOURCE_FILE_AND_ROW = "(__source_file_and_row__)"


# The data types for TrackingSlots. Default is "string"
TrackingSlotsTypes = {
    TrackingSlots.SOURCE_CLASS: "string",
    TrackingSlots.SOURCE_ROW: "integer",
    TrackingSlots.SOURCE_FILE: "string",
    TrackingSlots.SOURCE_FILE_AND_ROW: "string",
}
