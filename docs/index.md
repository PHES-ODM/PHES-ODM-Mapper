# PHES-ODM Mapper documentation

The PHES-ODM Mapper converts wastewater surveillance data between reporting
formats and the [Public Health Environmental Surveillance Open Data Model
(PHES-ODM)](https://phes-odm.org). You give it your existing data files, tell it
which conversion to perform, and it writes a set of CSV files in the target
format with the tables linked together by generated primary and foreign keys.

Each conversion is defined by a **module** — a directory of schemas, mapping
rules, filters, and ID-generation code. Four modules are built in, and you can
create your own for formats that are not covered.

## Run a mapping

After [installing](../README.md#installation), every mapping is run with the
same command shape — pick the module with `--module`, choose where the output
goes with `--output-dir`, and list the input files or directories last:

```console
odm-map --module <module-name> --output-dir <output-dir> <input> [<input> ...]
```

| Module | Source Format | Target Format |
| :------------------- | :------------ | :------------ |
| `odm-v1-to-v3` | ODM v1 | ODM v3 |
| `nwss-reporting-to-v3` | NWSS Reporting | ODM v3 |
| `pha4ge-to-v3` | PHA4GE | ODM v3 |
| `odm-v3-wide-to-long` | ODM v3 wide format | ODM v3 long format |

For what each module expects its input files to be called, see
[Supported Mappings](../README.md#supported-mappings). For a module you built
yourself, replace `--module` with `--module-path` and point it at the module
directory — see [Create a custom module](how-to/how_to.md#create-a-custom-module).

## Where to start

| If you are… | Read |
| --- | --- |
| New to the Mapper | [Tutorial: Your First Mapping](tutorials/tutorial.md) |
| Mapping your own data | [Choose which files and tables to map](how-to/how_to.md#choose-which-files-and-tables-to-map) |
| Building a module | [Create a custom module](how-to/how_to.md#create-a-custom-module), then [Module Configuration](reference/reference.md#module-configuration) |
| Writing a pipeline step | [Pipeline Actions](reference/actions/README.md) |
| Looking up an option | [Reference](reference/reference.md) |
| Debugging an unexpected result | [Debug a mapping that produced the wrong output](how-to/how_to.md#debug-a-mapping-that-produced-the-wrong-output) |
| Changing the code | [How the Mapper Works](explanation/explanation.md) and [Contributing](../CONTRIBUTING.md) |

Otherwise, browse by kind: the [tutorial](tutorials/tutorial.md) teaches,
[how-to guides](how-to/how_to.md) solve a specific task,
[reference](reference/reference.md) describes the file formats and options, and
[explanation](explanation/explanation.md) gives the background.

## Related repositories

- **[PHES-ODM-MapGenerator](https://github.com/PHES-ODM/PHES-ODM-MapGenerator)** —
  produces the LinkML-Map mapper YAML files that this repository's modules
  consume.
- **[PHES-ODM](https://github.com/PHES-ODM/PHES-ODM)** — the Open Data Model
  itself.
- **[linkml-map](https://github.com/linkml/linkml-map)** — the upstream
  transformation framework used by the [map](reference/actions/map.md) action.
