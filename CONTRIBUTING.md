# Contributing to PHES-ODM Mapper

Thank you for your interest in contributing to the PHES-ODM Mapper. This guide
covers everything you need to get started: setting up a development
environment, understanding the codebase, following code style requirements, and
submitting changes.

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
  - [Documentation](#documentation)
    - [The four kinds of document](#the-four-kinds-of-document)
    - [Keep docs in the same change as the code](#keep-docs-in-the-same-change-as-the-code)
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

The `odm-map` command is now available in your virtual environment. Any changes
you make to the source code in `odm_map/` take effect immediately.

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
│           ├── nwss-reporting-to-v3/      # NWSS Reporting → ODM v3
│           ├── odm-v1-to-v3/              # ODM v1 → ODM v3
│           ├── odm-v3-wide-to-long/       # ODM v3 wide format → ODM v3 long format
│           └── pha4ge-to-v3/              # PHA4GE → ODM v3
├── README.md                              # Landing page: install, supported mappings, doc map
├── CONTRIBUTING.md                        # This file
├── docs/                                  # Documentation, one directory per Diataxis section
│   ├── index.md                           # Landing page of the documentation site
│   ├── tutorials/                         # Learning-oriented, start to finish
│   │   └── tutorial.md                    # Tutorial: a complete first mapping
│   ├── how-to/                            # Task-oriented recipes
│   │   └── how_to.md                      # How-to guides: one section per problem
│   ├── reference/                         # Exact descriptions of every interface
│   │   ├── reference.md                   # Reference: CLI, Python API, module config.yaml
│   │   ├── actions/                       # One document per pipeline action
│   │   │   ├── README.md                  # Concepts common to all actions, plus the index
│   │   │   ├── clean.md                   # `clean` action
│   │   │   ├── drop_columns.md            # `drop_columns` action
│   │   │   ├── expand.md                  # `expand` action
│   │   │   ├── filter.md                  # `filter` action
│   │   │   ├── generate_ids.md            # `generate_ids` action
│   │   │   ├── map.md                     # `map` action
│   │   │   ├── prepare_wide_to_long.md    # `prepare_wide_to_long` action
│   │   │   ├── save.md                    # `save` action
│   │   │   └── select_enum_hierarchy.md   # `select_enum_hierarchy` action
│   │   ├── filters.md                     # Filter file reference
│   │   ├── id_generator.md                # ID code and ID config reference
│   │   └── wide_to_long_spec.md           # Wide-format column naming reference
│   ├── explanation/                       # Background reading and design specs
│   │   ├── explanation.md                 # Explanation: how the Mapper works
│   │   ├── merging_spec.md                # Design spec: merging separately-mapped datasets
│   │   └── long_to_wide_spec.md           # Design spec: long-to-wide mapping (in development)
│   └── img/                               # Images used in documentation
├── mkdocs.yml                             # Documentation site configuration
├── pyproject.toml                         # Package metadata and build configuration
├── requirements.txt                       # Python dependencies
└── requirements-docs.txt                  # Documentation build dependencies
```

## How the Mapper Works

[docs/explanation/explanation.md](docs/explanation/explanation.md) explains the
design: what a module is, what the pipeline does to the data, why IDs have to
be generated, and what the internal tracking and `_extra_` columns are for.
Read it before working on the pipeline. This section covers only what is
specific to the code.

The mapper executes a pipeline of actions defined in a module's `config.yaml`.
Input CSV/TSV/Excel files are first loaded into pandas DataFrames, one per
source table, and then `pipeline.py` dispatches each step to the corresponding
function in `odm_map/actions/`. Each action function is self-contained and
receives a `dict[str, list[pd.DataFrame]]` (a dictionary of class name → list
of DataFrames) and returns the same structure after modification.

Each action is documented in its own file under
[docs/reference/actions/](docs/reference/actions), with
[docs/reference/actions/README.md](docs/reference/actions/README.md) covering
what is common to all of them, and
[A typical pipeline order](docs/reference/actions/README.md#a-typical-pipeline-order)
showing the sequence most modules follow.

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and
formatting. The CI pipeline checks both on every push to `main` and on pull
requests targeting `main`. The target Python version is set by `target-version`
in `pyproject.toml`, so no command-line flag is needed.

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

A module is a self-contained directory with a `config.yaml` and all supporting
files. To add a new built-in module:

1. Create a new directory under `odm_map/data/modules/` using a descriptive
   kebab-case name, such as `my-source-to-v3`.

2. Write a `config.yaml` that defines the full transformation pipeline. See
   [Module Configuration](docs/reference/reference.md#module-configuration) for
   the complete configuration reference, and
   [docs/reference/actions/](docs/reference/actions) for the available actions
   and their parameters.

    At a minimum, the config requires:
    - `title`: A short human-readable description of the conversion.
    - `source_schema`: Path to the LinkML schema for the source format.
    - `steps`: A list of actions to perform.

3. Add the required files in subdirectories. Each action's document explains
   how to prepare the files it needs:

    | Subdirectory | Contents |
    |:-------------|:---------|
    | `schemas/`   | LinkML schema YAML files for the source and/or target datasets |
    | `mappers/`   | LinkML-Map YAML files that define field-level transformations ([map](docs/reference/actions/map.md)) |
    | `filters/`   | CSV files defining row-filtering rules ([filter](docs/reference/actions/filter.md)) |
    | `ids/`       | Excel or CSV ID code files and YAML ID config files ([generate_ids](docs/reference/actions/generate_ids.md)) |
    | `expander/`  | Expander YAML config ([expand](docs/reference/actions/expand.md)) |
    | `enum_hierarchy/` | Enum hierarchy YAML config ([select_enum_hierarchy](docs/reference/actions/select_enum_hierarchy.md)) |
    | `wide_to_long/` | Wide-to-long YAML config ([prepare_wide_to_long](docs/reference/actions/prepare_wide_to_long.md)) |

4. Use `{shared}` as a path prefix in `config.yaml` to reference files in the
   `_shared` module (e.g. `{shared}/schemas/odm_v3.yaml`).

5. Test your module:

    ```console
    odm-map --module my-source-to-v3 --output-dir path/to/output path/to/input
    ```

    You can also run with `--debug` to inspect intermediate data and
    `--temp-dir` to retain intermediate files.

## Adding a New Action

To add a new action type that can be used in a module `config.yaml`:

1. Create a new file `odm_map/actions/action_<name>.py`. The file should expose
   a single top-level function `action_<name>(data_frames, ...)` that accepts
   and returns a `dict[str, list[pd.DataFrame]]`.

2. Import and dispatch the new action in `odm_map/pipeline.py` by adding a new
   `elif action == "<name>":` branch in the `run` method.

3. Document the new action in its own file, `docs/reference/actions/<name>.md`,
   following the same structure as the existing action documents: what the
   action does, where it fits in a pipeline, a YAML example, a parameter table,
   and how to prepare any configuration or other files the action needs.

4. Add the new action to the index tables in
   [docs/reference/actions/README.md](docs/reference/actions/README.md),
   [docs/reference/reference.md](docs/reference/reference.md#steps), and
   [docs/explanation/explanation.md](docs/explanation/explanation.md#the-pipeline),
   and to the `docs/reference/actions/` tree in the [Project
   Structure](#project-structure) section above.

## Documentation

Documentation lives in [docs/](docs) and is indexed by
[docs/index.md](docs/index.md). It is built with
[MkDocs](https://www.mkdocs.org/) with the
[Material](https://squidfunk.github.io/mkdocs-material/) theme, and published to
GitHub Pages by [.github/workflows/docs.yaml](.github/workflows/docs.yaml) on
every push to `main`.

Preview the site locally. `requirements-docs.txt` holds only the site build
dependencies, so this works without installing the runtime packages:

```console
pip install -r requirements-docs.txt
mkdocs serve                       # http://127.0.0.1:8000
mkdocs build --strict              # what CI runs
```

CI also runs
[.github/scripts/check_doc_links.py](.github/scripts/check_doc_links.py), which
resolves every relative link and `#anchor` against the filesystem. `mkdocs.yml`
has to switch off MkDocs' own broken-link check, because these documents are
also read on GitHub and link to source files under `odm_map/` — targets that
live outside `docs/` and that MkDocs cannot resolve. Write those links relative
to the document (`../../odm_map/pipeline_cli.py` from `docs/reference/`,
`../../../odm_map/...` from `docs/reference/actions/`), not as `/odm_map/...`:
a leading `/` resolves against the domain root on both GitHub and the published
site, so such a link is broken in both places.

### The four kinds of document

Documentation follows the [Divio/Diátaxis](https://diataxis.fr/) framework. New
material belongs in exactly one of these — if it seems to fit two, it is
probably two pieces of writing.

- [docs/tutorials/tutorial.md](docs/tutorials/tutorial.md) — teaches a beginner
  by doing: followed start to finish, on sample data, with no alternatives or
  caveats mid-step.
- [docs/how-to/how_to.md](docs/how-to/how_to.md) — one section per stated
  problem: assumes competence, starts from a goal, links out rather than
  explaining.
- [docs/reference/reference.md](docs/reference/reference.md) and the documents
  it lists under [Further Reference Documents](docs/reference/reference.md#further-reference-documents) —
  describe the machinery: exhaustive, dry, and structured like the thing they
  describe.
- [docs/explanation/explanation.md](docs/explanation/explanation.md) — gives
  background and rationale: no instructions to follow.

The most common mistake is putting how-to material in a reference document. If
you catch yourself writing "first…, then…" in `docs/reference/reference.md`, it
belongs in `docs/how-to/how_to.md`.

When you add a page, also add it to the `nav` section of
[mkdocs.yml](mkdocs.yml), and to the table in
[docs/index.md](docs/index.md) or [README.md](README.md#documentation) if it is
a document a reader would look for by name.

### Keep docs in the same change as the code

Each fact is documented in exactly one place; the README links to `docs/` rather
than repeating it. Update the one place, not several.

| If you change | Also update |
| --- | --- |
| A command-line option | The Typer help text in `odm_map/pipeline_cli.py` and [docs/reference/reference.md](docs/reference/reference.md#command-line-interface) |
| The `Pipeline` class signature | [docs/reference/reference.md](docs/reference/reference.md#python-api) |
| A `config.yaml` key | [docs/reference/reference.md](docs/reference/reference.md#module-configuration) |
| An action's parameters | That action's document in [docs/reference/actions/](docs/reference/actions) |
| A new action | See [Adding a New Action](#adding-a-new-action) — one new document plus three index tables |
| A filter operation | [docs/reference/filters.md](docs/reference/filters.md) |
| The ID code or ID config format | [docs/reference/id_generator.md](docs/reference/id_generator.md) |
| The wide-column naming scheme | [docs/reference/wide_to_long_spec.md](docs/reference/wide_to_long_spec.md) |
| The pipeline, or an internal column | [docs/explanation/explanation.md](docs/explanation/explanation.md#the-pipeline) |
| A step a newcomer would trip over | [docs/tutorials/tutorial.md](docs/tutorials/tutorial.md) |
| A recurring support question | A new section in [docs/how-to/how_to.md](docs/how-to/how_to.md) |

**The one deliberate exception.** The command shape and the table of built-in
modules are repeated in [README.md](README.md#supported-mappings) and
[docs/index.md](docs/index.md), so that a new arrival at either landing page can
run a mapping without navigating anywhere. If you add or rename a module, update
both. Nothing else in the README is allowed to duplicate `docs/`.

## Submitting a Pull Request

1. Fork the repository and create a branch from `main`.
2. Make your changes, following the code style guidelines above.
3. Verify that `ruff check` and `ruff format --diff` both pass with no errors.
4. Push your branch and open a pull request against `main`.
5. Describe what your change does and why, and reference any relevant issues.