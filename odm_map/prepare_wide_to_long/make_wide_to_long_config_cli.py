from typing import Annotated, Union
import typer
from pathlib import Path
import yaml
import pandas as pd
import os

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
    def __init__(
        self, data_dictionary: Union[str, Path], config_template: Union[str, Path]
    ):
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

    def make(self, output_file: Union[str, Path]):
        # 1. Select all rows in data dictionary where mmaSet is not NA
        # 2. The partID maps onto that mmaSet
        #     part_id: mma_set
        # mma_sets_df = self.df[self.df[]]
        # print(output_file)
        self.config = {}
        self.config.update(self.config_template)

        # Select all rows in data dictionary where mmaSet is not NA
        mma_sets_df = self.df[~pd.isna(self.df["mmaSet"])]
        # Select the rows where partType is any of ["methods", "measurements"]
        mma_sets_df = mma_sets_df[
            mma_sets_df["partType"].isin(["methods", "measurements"])
        ]

        # Each partID (which are enumeration values) gets mapped onto the mmaSet
        partid_to_mmaset = {}
        for _, row in mma_sets_df[["partID", "mmaSet"]].iterrows():
            partid_to_mmaset[row[row.index[0]]] = row[row.index[1]]
        self.config["partid_to_mmaset"] = partid_to_mmaset

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
