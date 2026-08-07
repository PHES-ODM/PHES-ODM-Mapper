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
├── README.md                              # Landing page: install, supported mappings, doc map
├── CONTRIBUTING.md                        # This file
├── docs/                                  # Documentation
│   ├── tutorial.md                        # Tutorial: a complete first mapping
│   ├── how_to.md                          # How-to guides: task-oriented recipes
│   ├── reference.md                       # Reference: CLI, Python API, module config.yaml
│   ├── explanation.md                     # Explanation: how the Mapper works
│   ├── actions/                           # One document per pipeline action
│   │   ├── README.md                      # Concepts common to all actions, plus the index
│   │   ├── clean.md                       # `clean` action
│   │   ├── drop_columns.md                # `drop_columns` action
│   │   ├── expand.md                      # `expand` action
│   │   ├── filter.md                      # `filter` action
│   │   ├── generate_ids.md                # `generate_ids` action
│   │   ├── map.md                         # `map` action
│   │   ├── prepare_wide_to_long.md        # `prepare_wide_to_long` action
│   │   ├── save.md                        # `save` action
│   │   └── select_enum_hierarchy.md       # `select_enum_hierarchy` action
│   ├── filters.md                         # Filter file reference
│   ├── id_generator.md                    # ID code and ID config reference
│   ├── wide_to_long_spec.md               # Wide-format column naming reference
│   ├── merging_spec.md                    # Design spec: merging separately-mapped datasets
│   ├── long_to_wide_spec.md               # Design spec: long-to-wide mapping (in development)
│   └── img/                               # Images used in documentation
├── pyproject.toml                         # Package metadata and build configuration
└── requirements.txt                       # Python dependencies
```

## How the Mapper Works

[docs/explanation.md](docs/explanation.md) explains the design: what a module is, what the pipeline does to the data, why IDs have to be generated, and what the internal tracking and `_extra_` columns are for. Read it before working on the pipeline. This section covers only what is specific to the code.

The mapper executes a pipeline of actions defined in a module's `config.yaml`. Input CSV/TSV/Excel files are first loaded into pandas DataFrames, one per source table, and then `pipeline.py` dispatches each step to the corresponding function in `odm_map/actions/`. Each action function is self-contained and receives a `dict[str, list[pd.DataFrame]]` (a dictionary of class name → list of DataFrames) and returns the same structure after modification.

Each action is documented in its own file under [docs/actions/](docs/actions/), with [docs/actions/README.md](docs/actions/README.md) covering what is common to all of them, and [A typical pipeline order](docs/actions/README.md#a-typical-pipeline-order) showing the sequence most modules follow.

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

2. Write a `config.yaml` that defines the full transformation pipeline. See [Module Configuration](docs/reference.md#module-configuration) for the complete configuration reference, and [docs/actions/](docs/actions/) for the available actions and their parameters.

    At a minimum, the config requires:
    - `title`: A short human-readable description of the conversion.
    - `source_schema`: Path to the LinkML schema for the source format.
    - `steps`: A list of actions to perform.

3. Add the required files in subdirectories. Each action's document explains how to prepare the files it needs:

    | Subdirectory | Contents |
    |:-------------|:---------|
    | `schemas/`   | LinkML schema YAML files for the source and/or target datasets |
    | `mappers/`   | LinkML-Map YAML files that define field-level transformations ([map](docs/actions/map.md)) |
    | `filters/`   | CSV files defining row-filtering rules ([filter](docs/actions/filter.md)) |
    | `ids/`       | Excel or CSV ID code files and YAML ID config files ([generate_ids](docs/actions/generate_ids.md)) |
    | `expander/`  | Expander YAML config ([expand](docs/actions/expand.md)) |
    | `enum_hierarchy/` | Enum hierarchy YAML config ([select_enum_hierarchy](docs/actions/select_enum_hierarchy.md)) |
    | `wide_to_long/` | Wide-to-long YAML config ([prepare_wide_to_long](docs/actions/prepare_wide_to_long.md)) |

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

3. Document the new action in its own file, `docs/actions/<name>.md`, following the same structure as the existing action documents: what the action does, where it fits in a pipeline, a YAML example, a parameter table, and how to prepare any configuration or other files the action needs.

4. Add the new action to the index tables in [docs/actions/README.md](docs/actions/README.md), [docs/reference.md](docs/reference.md#steps), and [docs/explanation.md](docs/explanation.md#the-pipeline), and to the `docs/actions/` tree in the [Project Structure](#project-structure) section above.

## Submitting a Pull Request

1. Fork the repository and create a branch from `main`.
2. Make your changes, following the code style guidelines above.
3. Verify that `ruff check` and `ruff format --diff` both pass with no errors.
4. Push your branch and open a pull request against `main`.
5. Describe what your change does and why, and reference any relevant issues.