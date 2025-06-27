# %%
from typing import Annotated, List
import typer
from pathlib import Path

from odm_map.utils.cli_utils import get_input_data_files
from odm_map.enum_hierarchy.enum_hierarchy_selector import EnumHierarchySelector

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """For multivalued enum slots keep only the enumeration values that
have the deepest enum value in the hierarchy for the enumeration as
specified in a LinkML schema. That is, if the slot has multiple
values, then remove any of the values that is a parent (via the
is_a attribute in the LinkML schema) of any of the other values."""

SCHEMA_HELP = """The path to the LinkML schema that the data belong to."""

INPUTS_HELP = """The files and/or directories to select from. If a directory is
              specified then all recognized file types in that directory are
              loaded. File names determine which class the file belongs to."""

OUTPUT_DIR_HELP = """If specified then all data, after the selection is
                  performed, is saved to this directory."""

OUTPUT_FMT_HELP = """When --output-dir is specified, the names of the output
                  files are based on this string, where the string
                  interpolation tag {class_name} is used for specifying the
                  class name. For example, '{class_name}-sel.csv' will result
                  in 'measures-sel.csv' for the measures class."""


@app.command(help=MAIN_HELP)
def main(
    schema: Annotated[Path, typer.Argument(show_default=False, help=SCHEMA_HELP)],
    inputs: Annotated[List[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    output_dir: Annotated[
        Path, typer.Argument(show_default=False, help=OUTPUT_DIR_HELP)
    ],
    output_fmt: Annotated[
        str, typer.Option(show_default=False, help=OUTPUT_FMT_HELP)
    ] = "{class_name}.csv",
):
    data_files = get_input_data_files(inputs, schema=schema)
    selector = EnumHierarchySelector(schema)
    selector.select(data_files=data_files, output_dir=output_dir, output_fmt=output_fmt)


if __name__ == "__main__":
    if "get_ipython" in globals():
        opts = {
            "schema": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Mapper/PHES-ODM-Mapper/odm_map/data/modules/pha4ge-to-v2/schemas/pha4ge.yaml",
            "inputs": [
                "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Mapper/PHES-ODM-Mapper/gen/pha4ge-to-v2/temp/cleaned_data"
            ],
            "output_dir": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Mapper/PHES-ODM-Mapper/gen/pha4ge-to-v2/temp/cleaned_data/hierarchy",
            "output_fmt": "{class_name}.csv",
        }

        main(**opts)
    else:
        app()
