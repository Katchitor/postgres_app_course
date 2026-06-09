import importlib
from pathlib import Path, PurePath

package_dir = Path(__file__).parent


def load_all_in_package_folder(folder: PurePath, package: str) -> None:
    if not (folder / "__init__.py").exists():  # type: ignore
        return
    for child in Path(folder).iterdir():
        if child.name == "__init__.py":
            continue
        if child.name.endswith(".py"):
            module_name = child.stem
            importlib.import_module(f".{module_name}", package=package)
            continue
        if child.is_dir():
            load_all_in_package_folder(child, package + "." + child.name)


load_all_in_package_folder(package_dir, __name__)
