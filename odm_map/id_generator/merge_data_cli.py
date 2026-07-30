from pathlib import Path
from typing import Annotated

import typer

from odm_map.id_generator.merge_data import MergeData

MAIN_HELP = """Merge two or more datasets (that conform to a LinkML schema) by
ensuring there are no primary key conflicts."""

INPUTS_HELP = """Directories containing all data files to merge. Each directory
should contain data files named after the class name. Merging is performed in
order of how the directories are specified. The first dataset will also remain
unchanged, while all additional datasets might have their primary and foreign
keys changed to avoid conflicts."""

SCHEMA_HELP = """Path to the LinkML schema for the datasets."""

OUTPUT_DIR_HELP = """Directory to save all the merged data to."""

DEBUG_HELP = """If set then run in debug mode. In debug mode the outputs will
have extra columns with debug information, and rows will not be dropped based
on duplicate primary keys, instead a new column named __drop will be added and
set to True if that row would be dropped if not run in debug mode."""

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[list[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    schema: Annotated[Path, typer.Option(show_default=False, help=SCHEMA_HELP)],
    output_dir: Annotated[Path, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    debug: Annotated[bool, typer.Option(show_default=True, help=DEBUG_HELP)] = False,
):
    merge = MergeData(inputs=inputs, schema=schema)
    merge.merge(
        output_dir, multi_bar_progress="get_ipython" not in globals(), debug=debug
    )


if __name__ == "__main__":
    app()
