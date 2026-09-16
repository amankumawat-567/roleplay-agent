import yaml


class LiteralDumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


LiteralDumper.add_representer(str, _str_presenter)


def dump_yaml(data: dict, path) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, Dumper=LiteralDumper, sort_keys=False, allow_unicode=True, width=1000)
