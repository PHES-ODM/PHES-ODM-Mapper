import os
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
import yaml

from odm_map.prepare_wide_to_long.wide_column_utils import ConfigKeys
from odm_map.utils.general_utils import read_data_frame
from odm_map.utils.logger import get_logger

MAIN_HELP = """Generate the configuration file needed for the
WideColumnExpander to run for ODM wide tables."""

DATA_DICTIONARY_HELP = """The Excel ODM data dictionary file."""

OUTPUT_FILE_HELP = """The output YAML file to save the generated configuration
to."""

CONFIG_TEMPLATE_HELP = """The YAML configuration file that is used as a template to
build the final configuration from. This template is loaded, and new keys/values are
added to it to create the final configuration file."""

logger = get_logger(__name__)

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)


class MakeWideToLongConfig:
    def __init__(self, data_dictionary: str | Path, config_template: str | Path):
        self.df = read_data_frame(
            data_dictionary,
            sheet_name="parts",
            na_values={"parts": {"partID": ""}, "sets": {"partID": ""}},
        )
        self.df = self.df[self.df["status"] == "active"].reset_index(drop=True).copy()

        if config_template:
            with open(config_template, "r") as f:
                self.config_template = yaml.safe_load(f)
        else:
            self.config_template = {}

    def make(self, output_file: str | Path):
        self.config = {}
        self.config.update(self.config_template)

        # When setting protocolSteps.method or protocolSteps.measure, the value we set
        # will determine which enumeration values protocolSteps.value can take on.
        # These enumeration sets (called mmaSets for "measure, method, attribute sets") are subsets
        # of the larger "methods" and "measurements" sets. The mapping partid_to_mmaset
        # tells us which mmaSet to use for a given method/measure value. This is also
        # the case in the measures table, where the value found in measures.measure
        # determines which values measures.value can take on.
        # Select all rows in data dictionary where mmaSet is not NA
        mma_sets_df = self.df[~pd.isna(self.df["mmaSet"])]
        # Select the rows where partType is any of ["methods", "measurements"]
        mma_sets_df = mma_sets_df[
            mma_sets_df["partType"].isin(["methods", "measurements"])
        ]
        # Each partID (which are enumeration values) gets mapped onto the mmaSet
        partid_to_mmaset = {}
        for _, row in mma_sets_df[["partID", "mmaSet"]].iterrows():
            partid_to_mmaset[row["partID"]] = row["mmaSet"]
        self.config[ConfigKeys.PARTID_TO_MMASET] = partid_to_mmaset

        # Get all the tables, and their shortcodes stored in partInstr
        tables_df = self.df[self.df["partType"] == "tables"]
        tables_to_shortnames = {}
        for _, row in tables_df[["partID", "partInstr"]].iterrows():
            tables_to_shortnames[row["partID"]] = row["partInstr"]
        self.config[ConfigKeys.TABLES_TO_SHORTNAMES] = tables_to_shortnames

        # Save config to disk
        logger.info(f"Saving to {output_file}")
        if os.path.dirname(output_file):
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w") as f:
            yaml.safe_dump(self.config, f, sort_keys=False)


@app.command(help=MAIN_HELP)
def main(
    data_dictionary: Annotated[
        Path, typer.Option(show_default=False, help=DATA_DICTIONARY_HELP)
    ],
    config_template: Annotated[
        Path, typer.Option(show_default=False, help=CONFIG_TEMPLATE_HELP)
    ],
    output_file: Annotated[
        Path, typer.Option(show_default=False, help=OUTPUT_FILE_HELP)
    ],
):
    config = MakeWideToLongConfig(
        data_dictionary=data_dictionary, config_template=config_template
    )
    config.make(output_file)


if __name__ == "__main__":
    app()
