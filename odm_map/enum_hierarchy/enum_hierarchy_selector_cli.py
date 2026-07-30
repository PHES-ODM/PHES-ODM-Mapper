from pathlib import Path
from typing import Annotated

import typer

from odm_map.enum_hierarchy.enum_hierarchy_selector import EnumHierarchySelector
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """For multivalued enum slots keep only the enumeration values that
have the deepest enum value in the hierarchy for the enumeration as specified
in a LinkML schema. That is, if the slot has multiple values, then remove any
of the values that is a parent (via the is_a attribute in the LinkML schema) of
any of the other values."""

INPUTS_HELP = """The files and/or directories to select from. If a directory is
specified then all recognized file types in that directory are loaded. File
names determine which class the file belongs to."""

SCHEMA_HELP = """The path to the LinkML schema that the data belong to."""

OUTPUT_DIR_HELP = """Directory to save the results to."""

OUTPUT_FMT_HELP = """The names of the output files are based on this string,
where the string interpolation tag {class_name} is used for specifying the
class name. For example, '{class_name}-sel.csv' will result in
'measures-sel.csv' for the measures class."""

CONFIG_HELP = """Optional path to the config to use. The config specifies which
classes and slots to select enum values from. If no config is provided then all
classes and slots that are multi-valued enums are selected."""


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[list[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    schema: Annotated[Path, typer.Option(show_default=False, help=SCHEMA_HELP)],
    output_dir: Annotated[Path, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    output_fmt: Annotated[
        str, typer.Option(show_default=False, help=OUTPUT_FMT_HELP)
    ] = "{class_name}.csv",
    config: Annotated[
        Path | None, typer.Option(show_default=False, help=CONFIG_HELP)
    ] = None,
):
    data_files = get_input_data_files(inputs, schema=schema)
    selector = EnumHierarchySelector(schema, config=config)
    selector.select(data_files=data_files, output_dir=output_dir, output_fmt=output_fmt)


if __name__ == "__main__":
    app()
