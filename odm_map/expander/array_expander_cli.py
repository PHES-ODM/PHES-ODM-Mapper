# %%
from typing import List, Annotated
import typer
from pathlib import Path

from odm_map.expander.array_expander import ArrayExpander
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(pretty_exceptions_show_locals=False, rich_markup_mode="rich")

MAIN_HELP = """Expand rows in data by looking for arrays in specified columns,
and duplicating the rows for each item in the array."""

INPUTS_HELP = """One or more inputs. Either paths to CSV, TSV, TXT, YAML, YML,
or XLSX files, or directories that contain these types of files
to use for input."""

CONFIG_HELP = """Path to the configuration file."""

MAX_ROWS_HELP = """Maximum number of rows to load from each input file. If 0
                then all rows are loaded."""

OUTPUT_DIR_HELP = """If specified, then save the resulting DataFrames to disk.
                  Before saving we merge all the data from each class together,
                  so that we only have one file per class."""


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[List[Path], typer.Argument(show_default=False, help=INPUTS_HELP)],
    config: Annotated[Path, typer.Option(show_default=False, help=CONFIG_HELP)],
    output_dir: Annotated[Path, typer.Option(help=OUTPUT_DIR_HELP)] = None,
    max_rows: Annotated[int, typer.Option(help=MAX_ROWS_HELP)] = 0,
):
    data_files = get_input_data_files(inputs, schema=None)
    expander = ArrayExpander(config=config)
    expander.expand_data(
        data_files=data_files,
        data_frames=None,
        output_dir=output_dir,
        max_rows=max_rows,
    )


if __name__ == "__main__":
    if "get_ipython" in globals():
        opts = {
            "inputs": ["../../gen/pha4ge-to-v2/temp/mapped_data"],
            "config": "../data/modules/pha4ge-to-v2/expander/expander_config.yaml",
            "output_dir": "../../gen/pha4ge-to-v2/expanded",
            "max_rows": 0,
        }
        main(**opts)
    else:
        app()
