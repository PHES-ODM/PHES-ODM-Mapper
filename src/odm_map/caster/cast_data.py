from typing import Union, Dict, List, Any
import pandas as pd
from pathlib import Path
import dateutil.parser

from linkml_runtime import SchemaView


class CastData(object):
    def __init__(
        self,
        data: Dict[str, List[pd.DataFrame]],
        df: pd.DataFrame,
        schema: Union[SchemaView, str, Path],
    ):
        if isinstance(schema, (str, Path)):
            self.schema = SchemaView(schema)
        else:
            self.schema = schema

        self.data = data

    def cast_data(self):
        for class_name, all_data in self.data.items():
            class_defn = self.schema.induced_class(class_name)
            for attr_name, attr_defn in class_defn.attributes.items():
                for df in all_data:
                    if attr_defn.range == "datetime":
                        df[attr_name] = df[attr_name].apply(self.parse_datetime)

    def parse_datetime(self, d, ignoretz=True) -> Any:
        if not d or not isinstance(d, str):
            return d
        try:
            return dateutil.parser.parse(d, ignoretz=ignoretz).isoformat()
        except Exception:
            return d
