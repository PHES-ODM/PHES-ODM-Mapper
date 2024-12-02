# %%
import os
import pandas as pd
from typing import List
import numpy as np

# dir1 = "../gen/odm-v1-to-v2/test"
# dir2 = "../gen/odm-v1-to-v2"
# dir1 = "../gen/nwss-reporting-to-v2-test-csv"
# dir2 = "../gen/nwss-reporting-to-v2-test-excel"
# dir1 = "../gen/test/mapped_data_ids"
# dir2 = "../gen/test/mapped_data_ids-new"

dir1 = "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Mapper/PHES-ODM-Mapper/gen/odm-v1-to-v2-test-excel"
dir2 = "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Mapper/PHES-ODM-Mapper/gen/odm-v1-to-v2-test-csv"


def file_allowed(file: str, files_list: List[str]) -> bool:
    def _clean_file_name(f: str) -> str:
        name, ext = os.path.splitext(f)
        name = name.split("-")[0]
        return f"{name}{ext}"

    files_list = [_clean_file_name(f) for f in files_list]
    return _clean_file_name(file) in files_list


files1 = sorted([f for f in os.listdir(dir1) if os.path.splitext(f)[-1] == ".csv"])
files2 = sorted([f for f in os.listdir(dir2) if os.path.splitext(f)[-1] == ".csv"])

files1 = [f for f in files1 if file_allowed(f, files2)]
files2 = [f for f in files2 if file_allowed(f, files1)]

OUTPUT_MISMATCHES = True
IGNORE_COLUMNS = [
    "__hash",
    "(__source_file_and_row__)",
    "(__source_file__)",
    "(__source_row__)",
]

total_rows = 0
total_drop_rows = 0
has_mismatches = False

for file1, file2 in zip(files1, files2):
    df1 = pd.read_csv(
        os.path.join(dir1, file1),
        low_memory=False,
        keep_default_na=False,
        na_values=None,
    )
    df2 = pd.read_csv(
        os.path.join(dir2, file2),
        low_memory=False,
        keep_default_na=False,
        na_values=None,
    )
    total_rows += len(df1)
    if "__drop" in df1.columns:
        drop = df1["__drop"].map(lambda x: isinstance(x, str) and x in ["True"])
        total_drop_rows += int(drop.sum())

    df1 = df1[
        [c for c in df1.columns if c not in IGNORE_COLUMNS and not c.startswith("_")]
    ]
    df2 = df2[
        [c for c in df2.columns if c not in IGNORE_COLUMNS and not c.startswith("_")]
    ]

    matches = (df1 == df2) | (pd.isna(df1) & pd.isna(df2))
    coords = np.where(~matches)
    coords = list(zip(coords[0], coords[1]))
    coords = [(y, df1.columns[x]) for y, x in coords]
    if len(coords):
        if OUTPUT_MISMATCHES:
            vals = [
                (df1.loc[coord[0], coord[1]], df2.loc[coord[0], coord[1]])
                for coord in coords
            ]
            msg = [
                f"{file1}: {coord}: {val1} vs {val2}"
                for coord, (val1, val2) in zip(coords, vals)
            ]
            msg = "\n    ".join([""] + msg)
        else:
            msg = f"{len(coords)} mismatches!"
        print(f"*** {file1} != {file2} ({len(df1)} rows): {msg}")
        has_mismatches = True
    else:
        print(f"{file1} == {file2} ({len(df1)} rows)")

print("Found mismatches!" if has_mismatches else "No mismatches, all good")
print(
    f"Total rows: {total_rows}, total drop rows: {total_drop_rows}, rows after dropping: {total_rows - total_drop_rows}"
)
