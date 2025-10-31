from typing import Annotated
from pathlib import Path
import typer

from odm_map.prepare_wide_to_long.wide_column_idcode_maker import WideColumnIDCodeMaker

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """Create ID code generation files for linking IDs between output tables for
wide-to-long mapping."""

INPUT_HELP = """Path to data file that we need to generate ID code for."""

TARGET_SCHEMA_HELP = """Path to the LinkML schema that the target mapped data is for
(eg. for ODM v3 long format)."""

OUTPUT_DIR_HELP = """If specified, then the directory to save the ID code to."""

CONFIG_HELP = """The YAML configuration file."""

EXPANDED_META_HELP = """The YAML configuration file that contains meta information
about the input expanded data. This includes information such as which groups are
explicitely defined vs implicitly defined (in the original wide data), and other
meta information. It is created by the wide column expander."""

SOURCE_CLASS_HELP = """The name of the source class in the mapping."""


@app.command(help=MAIN_HELP)
def main(
    input: Annotated[Path, typer.Argument(show_default=False, help=INPUT_HELP)],
    config: Annotated[Path, typer.Option(show_default=False, help=CONFIG_HELP)],
    expanded_meta: Annotated[
        Path, typer.Option(show_default=False, help=EXPANDED_META_HELP)
    ],
    target_schema: Annotated[
        Path, typer.Option(show_default=False, help=TARGET_SCHEMA_HELP)
    ],
    source_class: Annotated[
        str, typer.Option(show_default=False, help=SOURCE_CLASS_HELP)
    ],
    output_dir: Annotated[
        Path, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)
    ] = None,
):
    maker = WideColumnIDCodeMaker(
        config=config,
        expanded_meta=expanded_meta,
        source_class_name=source_class,
        target_schema=target_schema,
    )
    maker.make(data_file=input, data_frame=None, output_dir=output_dir)


if __name__ == "__main__":
    app()
