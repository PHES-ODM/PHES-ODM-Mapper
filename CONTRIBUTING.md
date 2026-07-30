# Contributing to PHES-ODM Mapper

Thank you for your interest in contributing to the PHES-ODM Mapper. This guide covers everything you need to get started: setting up a development environment, understanding the codebase, following code style requirements, and submitting changes.

## Table of Contents

- [Contributing to PHES-ODM Mapper](#contributing-to-phes-odm-mapper)
  - [Table of Contents](#table-of-contents)
  - [Development Environment Setup](#development-environment-setup)
    - [Requirements](#requirements)
    - [Steps](#steps)
  - [Project Structure](#project-structure)
  - [How the Mapper Works](#how-the-mapper-works)
    - [Key Concepts](#key-concepts)
  - [Code Style](#code-style)
  - [Adding a New Built-In Module](#adding-a-new-built-in-module)
  - [Adding a New Action](#adding-a-new-action)
  - [Submitting a Pull Request](#submitting-a-pull-request)

## Development Environment Setup

### Requirements

- Python 3.10 or higher

### Steps

1. Clone the repository:

    ```console
    git clone git@github.com:PHES-ODM/PHES-ODM-Mapper.git
    cd PHES-ODM-Mapper
    ```

2. Create a virtual environment:

    ```console
    python -m venv .env
    ```

3. Activate the virtual environment on Linux/macOS:

    ```console
    source .env/bin/activate
    ```

    Or on Windows:

    ```console
    .env\Scripts\activate
    ```

4. Install the package in editable mode (changes to the source are reflected immediately without reinstalling):

    ```console
    pip install -e .
    ```

5. Install the linter:

    ```console
    pip install ruff
    ```

The `odm-map` command is now available in your virtual environment. Any changes you make to the source code in `odm_map/` take effect immediately.

## Project Structure

```
PHES-ODM-Mapper/
├── odm_map/                               # Main Python package
│   ├── pipeline.py                        # Core Pipeline class — Python API entry point
│   ├── pipeline_cli.py                    # CLI entry point (the `odm-map` command)
│   ├── actions/                           # One file per pipeline action type
│   │   ├── action_clean_data.py           # `clean` action
│   │   ├── action_drop_columns.py         # `drop_columns` action
│   │   ├── action_expand_data.py          # `expand` action
│   │   ├── action_filter_data.py          # `filter` action
│   │   ├── action_generate_ids.py         # `generate_ids` action
│   │   ├── action_map_data.py             # `map` action
│   │   ├── action_prepare_wide_to_long.py # `prepare_wide_to_long` action
│   │   ├── action_save_data.py            # `save` action
│   │   └── action_select_enum_hierarchy.py# `select_enum_hierarchy` action
│   ├── cleaner/                           # Data cleaning logic
│   ├── column_dropper/                    # Column dropping logic
│   ├── enum_hierarchy/                    # Enum hierarchy selector logic
│   ├── expander/                          # Array expansion logic
│   ├── filter/                            # Row filtering logic
│   ├── id_generator/                      # ID and primary/foreign key generation
│   ├── mapper/                            # Wrapper around LinkML-Map
│   ├── prepare_wide_to_long/              # Wide-to-long format transformer
│   ├── prepare_long_to_wide/              # Long-to-wide format transformer (in development)
│   ├── progress/                          # Progress bar utilities
│   ├── utils/                             # General utilities (CLI helpers, schema utilities, etc.)
│   └── data/
│       └── modules/                       # Built-in conversion modules
│           ├── _shared/                   # Schemas, IDs, and filters shared across modules
│           ├── nwss-reporting-to-v2/      # NWSS Reporting → ODM v2
│           ├── odm-v1-to-v2/              # ODM v1 → ODM v2
│           ├── odm-v3-wide-to-long/       # ODM v3 wide format → ODM v3 long format
│           └── pha4ge-to-v2/              # PHA4GE → ODM v2
├── README.md                              # Main documentation
├── CONTRIBUTING.md                        # This file
├── docs/                                  # Documentation
│   ├── custom_modules.md                  # Full reference for creating custom modules
│   ├── filters.md                         # Filter system reference
│   ├── id_generator.md                    # ID generator reference
│   ├── merging_spec.md                    # Design spec for merging separately-mapped datasets
│   ├── wide_to_long_spec.md               # Implementation spec for wide-to-long mapping
│   ├── long_to_wide_spec.md               # Implementation spec for long-to-wide mapping (in development)
│   └── img/                               # Images used in documentation
├── pyproject.toml                         # Package metadata and build configuration
└── requirements.txt                       # Python dependencies
```

## How the Mapper Works

The mapper executes a pipeline of actions defined in a module's `config.yaml` file. The typical flow is:

1. **Load data** — Input CSV/TSV/Excel files are loaded into pandas DataFrames, one per source table.
2. **`clean`** — Normalize column names, correct enumeration values, and check regex patterns against a LinkML schema.
3. **`select_enum_hierarchy`** *(optional)* — For multivalued enum slots, remove parent values when a more specific child value is present.
4. **`map`** — Use LinkML-Map YAML schemas to transform DataFrames from the source format to the target format.
5. **`expand`** *(optional)* — Expand rows that contain multi-valued arrays so that each value gets its own row.
6. **`filter`** — Remove unwanted rows (e.g. rows with blank required values, or rows with sentinel values like `<ignore>`).
7. **`generate_ids`** — Create primary and foreign keys to link tables together.
8. **`drop_columns`** — Remove internal tracking and `_extra_` columns from the output.
9. **`save`** — Write the final DataFrames to CSV files.

The `pipeline.py` file dispatches each step to the corresponding function in `odm_map/actions/`. Each action function is self-contained and receives a `dict[str, list[pd.DataFrame]]` (a dictionary of class name → list of DataFrames) and returns the same structure after modification.

### Key Concepts

**Modules** are directories containing a `config.yaml` and all supporting files (LinkML schemas, LinkML-Map mapper files, filter CSVs, ID code files). The built-in modules live in `odm_map/data/modules/`. Custom modules can live anywhere on disk.

**Tracking columns** are internal columns added automatically during the `map` step. They record the source file and row number each output row came from, which is used by the ID generator for linking between tables. They are named `(__source_file_and_row__)`, `(__source_file__)`, and `(__source_row__)`.

**`_extra_` columns** are additional non-schema columns added by the mapper or ID generator to carry temporary data needed during processing (e.g. tags used for linking between tables). They are stripped before saving the final output.

**The `_shared` module** at `odm_map/data/modules/_shared/` contains LinkML schemas, ID code files, and filter files shared by multiple modules. Use `{shared}` as a path prefix in a `config.yaml` to reference files from this directory.

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. The CI pipeline checks both on every push to `main` and on pull requests targeting `main`. The target Python version is set by `target-version` in `pyproject.toml`, so no command-line flag is needed.

Check for lint errors:

```console
ruff check
```

Check formatting without making changes:

```console
ruff format --diff
```

Apply formatting automatically:

```console
ruff format
```

All code must pass both checks before a pull request can be merged.

## Adding a New Built-In Module

A module is a self-contained directory with a `config.yaml` and all supporting files. To add a new built-in module:

1. Create a new directory under `odm_map/data/modules/` using a descriptive kebab-case name, such as `my-source-to-v3`.

2. Write a `config.yaml` that defines the full transformation pipeline. See [custom_modules.md](docs/custom_modules.md) for the complete configuration reference and all available actions.

    At a minimum, the config requires:
    - `title`: A short human-readable description of the conversion.
    - `source_schema`: Path to the LinkML schema for the source format.
    - `steps`: A list of actions to perform.

3. Add the required files in subdirectories:

    | Subdirectory | Contents |
    |:-------------|:---------|
    | `schemas/`   | LinkML schema YAML files for the source and/or target datasets |
    | `mappers/`   | LinkML-Map YAML files that define field-level transformations |
    | `filters/`   | CSV files defining row-filtering rules |
    | `ids/`       | Excel or CSV ID code files and YAML ID config files |
    | `expander/`  | Expander YAML config (if using the `expand` action) |
    | `wide_to_long/` | Wide-to-long config (if using `prepare_wide_to_long`) |

4. Use `{shared}` as a path prefix in `config.yaml` to reference files in the `_shared` module (e.g. `{shared}/schemas/odm_v3.yaml`).

5. Test your module:

    ```console
    odm-map --module my-source-to-v3 --output-dir path/to/output path/to/input
    ```

    You can also run with `--debug` to inspect intermediate data and `--temp-dir` to retain intermediate files.

## Adding a New Action

To add a new action type that can be used in a module `config.yaml`:

1. Create a new file `odm_map/actions/action_<name>.py`. The file should expose a single top-level function `action_<name>(data_frames, ...)` that accepts and returns a `dict[str, list[pd.DataFrame]]`.

2. Import and dispatch the new action in `odm_map/pipeline.py` by adding a new `elif action == "<name>":` branch in the `run` method.

3. Document the new action in [custom_modules.md](docs/custom_modules.md) under the **Actions** section, including a YAML example and a parameter table.

## Submitting a Pull Request

1. Fork the repository and create a branch from `main`.
2. Make your changes, following the code style guidelines above.
3. Verify that `ruff check` and `ruff format --diff` both pass with no errors.
4. Push your branch and open a pull request against `main`.
5. Describe what your change does and why, and reference any relevant issues.