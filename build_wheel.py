"""
Copyright 2026 Static Codes

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

"""
A simple wheel packager using only the stdlib; fully local: no external deps, or network reqs are required.

How it works:
1. Reads the project metadata from pyproject.toml.
2. Writes the equivalent project fields into a .dist-info file.
3. Packages src/ into a .whl and writes it to ./dist/.

Intended Limitations:
- `dependency-groups` is not queried, as it was not required for my workflow.
- hatchling artifacts are not bundled, as I once again did not require them.

Usage:
    - Windows:
        cd path\\to\\website-clone
        python build_wheel.py

    - macOS/Linux:
        cd path/to/website-clone
        python3 build_wheel.py


"""

######## Imports ########

import base64
import datetime
import hashlib
import re
import tomllib
import zipfile
from pathlib import Path
from typing import Optional



######## Consts ########

ROOT_DIRECTORY = Path(__file__).resolve().parent
SOURCE_DIRECTORY = ROOT_DIRECTORY / "uaforge"
DISTRIBUTION_DIRECTORY = ROOT_DIRECTORY / "dist"

WHEEL_DATA = b"Wheel-Version: 1.0\nGenerator: build_wheel.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
meta_tag = None
pyproject = None



######## Helper funcs #########

def add_record(name: str, data: bytes) -> str:
    digested_hash = hashlib.sha256(data).digest()
    encoded_digest = base64.urlsafe_b64encode(digested_hash)
    digest = encoded_digest.rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"

def find_modules_in_pyproject() -> list[Path]:
    """Iterates through the src directory and returns all modules in the same subdirectory as an __init__.py file."""
    
    if SOURCE_DIRECTORY.is_dir():
        
        found = sorted(package for package in SOURCE_DIRECTORY.iterdir() 
            if package.is_dir() and 
            (package / "__init__.py").exists()
        )
        if found:
            return found
    
    raise SystemExit("No Python package found (expected src/website_clone/__init__.py).")

def find_version_in_pyproject() -> str:
    global meta_tag
    
    if "version" in meta_tag:
        return str(meta_tag["version"])
    
    raise SystemExit("Dynamic versions are not supported; `version` must be a constant value in pyproject.toml.")

def get_readme_data(output: list) -> Optional[str]:
    readme_tag = meta_tag.get("readme")
    
    if readme_tag:
        path = ROOT_DIRECTORY / (readme_tag if isinstance(readme_tag, str) else readme_tag["file"])
        
        # This may need another edge case, in the wild I've only seen .MD, .txt, or no ext used.
        kind = "text/markdown" if path.suffix.lower() == ".md" else "text/plain"
        output.append(f"Description-Content-Type: {kind}")
        return path.read_text(encoding="utf-8")
    return ""
    
def pad_unix_permission_attrs_for_windows_compliance(info: zipfile.ZipInfo) -> None:
    """
    ZipInfo.external_attr is a 32 bit int, 0-15 are Windows (MS-DOS) attrs and 16-31 are Unix attrs.
    After the bitshift is performed the first 16 bits are zeroed and the last 16 bits are ignored by windows. 

    Int Repr: 644 
    Unix Repr: (drw-r--r--) | Owner read-write + user/group read-only on directory
    Raw Binary Repr: 00000000000000000000001010000100
    """
    info.external_attr = int(0o644) << 16




######## Metadata functionality #########

def add_author_to_metadata(output: list) -> None:
    """
    Parses the provided meta dict for the 'authors' block
    then conditionally appends the equivalent wheel setup field.
    """

    global meta_tag
    for author in meta_tag.get("authors", []):
        # Handling the name and email field.
        if author.get("name") and author.get("email"):
            output.append(f"Author-email: {author['name']} <{author['email']}>")
        # Handling just the name field.
        elif author.get("name"):
            output.append(f"Author: {author['name']}")
        # Handling just an email field.
        elif author.get("email"):
            output.append(f"Author-email: {author['email']}")

def add_license_info_to_metadata(output: list) -> None:
    global meta_tag

    # Adding the license (License-Expression)
    if isinstance(meta_tag.get("license"), str):
        output.append(f"License-Expression: {meta_tag['license']}")
    
    # Appending any license files provided.
    # Currently website-clone only has one license file;
    # By sorting via a root glob, any additional license files will be picked up, making this relatively future-proof.
    for patterns in meta_tag.get("license-files", []):
        output += [f"License-File: {pattern.name}" for pattern in sorted(ROOT_DIRECTORY.glob(patterns))]

def add_dependencies_to_metadata(output: list) -> None:
    global meta_tag
    if meta_tag.get("requires-python"):
        output.append(f"Requires-Python: {meta_tag['requires-python']}")

    output += [f"Requires-Dist: {dependency}" for dependency in meta_tag.get("dependencies", [])]
    
    for provides_extra, requires_dist in meta_tag.get("optional-dependencies", {}).items():
        output.append(f"Provides-Extra: {provides_extra}")
        output += [f'Requires-Dist: {require_dist}; extra == "{provides_extra}"' for require_dist in requires_dist]

def build_wheel_metadata(version: str) -> str:
    global meta_tag

    output = [
        "Metadata-Version: 2.4", 
        f"Name: {meta_tag['name']}", 
        f"Version: {version}"
    ]

    if meta_tag.get("description"):
        output.append(f"Summary: {meta_tag['description']}")

    if meta_tag.get("keywords"):
        output.append("Keywords: " + ",".join(meta_tag["keywords"]))
    
    # Adds: Name, Email
    add_author_to_metadata(output)

    # Adds: License-Expression, License-File
    add_license_info_to_metadata(output)
    
    output += [f"Classifier: {classifier}" for classifier in meta_tag.get("classifiers", [])]
    output += [f"Project-URL: {key}, {val}" for key, val in meta_tag.get("urls", {}).items()]
    
    add_dependencies_to_metadata(output)
    
    # This will be populated if the pyproject is ever to reference the project's readme.
    readme_body = get_readme_data(output)
    
    # pip is Unix based so using Linux line endings on Windows are not a concern.
    return "\n".join(output) + "\n\n" + readme_body




######## Packaging functionality ########

def add_wheel_dist_info_packages(dist_info_files: list[tuple[str, bytes]]) -> None:
    # Matches all packages in the .toml file.
    for package in find_modules_in_pyproject():
        
        # Matches all package paths, then iterates through them.
        for path in sorted(package.rglob("*")):

            # Ignoring pycache artifacts.
            if (path.is_file() and 
                "__pycache__" not in path.parts and 
                path.suffix not in {".pyc", ".pyo"}
            ):
                # Despite it's name PosixPath is fully compliant with both Unix and NT.
                relative_posix_path = path.relative_to(package.parent).as_posix()
                dist_info_files.append((relative_posix_path, path.read_bytes()))
                
def add_wheel_dist_info_scripts(dist_info_files: list[tuple[str, bytes]], dist_info_subdir: str) -> None:
    global meta_tag
    scripts = meta_tag.get("scripts", {})
    if scripts:
        entry = "[console_scripts]\n" + "".join(f"{key} = {val}\n" for key, val in scripts.items())
        dist_info_files.append((f"{dist_info_subdir}/entry_points.txt", entry.encode()))

def add_wheel_dist_info_licenses(dist_info_files: list[tuple[str, bytes]], dist_info_subdir: str) -> None:
    for patterns in meta_tag.get("license-files", []):
        for pattern in sorted(ROOT_DIRECTORY.glob(patterns)):
            dist_info_files.append((f"{dist_info_subdir}/licenses/{pattern.name}", pattern.read_bytes()))

def add_wheel_dist_info_records(dist_info_files: list[tuple[str, bytes]], dist_info_subdir: str) -> None:
    
    records = [add_record(name, data) for name, data in dist_info_files] + [f"{dist_info_subdir}/RECORD,,"]

    record_filepath = f"{dist_info_subdir}/RECORD"

    record_data = ("\n".join(records) + "\n").encode()

    dist_info_files.append((record_filepath, record_data))

def add_wheel_dist_info_subdir(dist_info_files: list[tuple[str, bytes]], dist_info_subdir: str, version: str) -> None:
    
    # Inserting referenced packages from the pyproject to ./dist/wheel-name.whl/wheel-name.dist-info/<package>
    add_wheel_dist_info_packages(dist_info_files)
    
    # Currently returns:
    # Metadata-Version: 2.4
    # Name: website-clone
    # Version: 0.1.0
    # Summary: High-fidelity website capture and offline replay
    # Requires-Python: >=3.11
    # Requires-Dist: playwright==1.62.0
    # Requires-Dist: tinycss2==1.5.1
    metadata: str = build_wheel_metadata(version).encode()

    # dist_info_subdir/METADATA
    dist_info_files.append((f"{dist_info_subdir}/METADATA", metadata))
    
    # dist_info_subdir/WHEEL
    dist_info_files.append((f"{dist_info_subdir}/WHEEL", WHEEL_DATA))

    # dist_info_subdir/scripts/<script>
    add_wheel_dist_info_scripts(dist_info_files, dist_info_subdir)
    
    # dist_info_subdir/licenses/<license>
    add_wheel_dist_info_licenses(dist_info_files, dist_info_subdir)
    
    # dist_info_subdir/RECORD
    # Entry format: file,sha256=<hash>,<size_in_bytes>
    add_wheel_dist_info_records(dist_info_files, dist_info_subdir)

def create_wheel_archive(dist_info_files: list[tuple[str, bytes]], wheel_file: str):
    DISTRIBUTION_DIRECTORY.mkdir(exist_ok=True)
    
    with zipfile.ZipFile(wheel_file, "w", zipfile.ZIP_DEFLATED) as file:

        # Stored as (Year, Month, Day, Hour, Minute, Second) 
        # Strips off Weekday, YearDay, and IsDst.
        # Ref: https://docs.python.org/3/library/time.html#time.struct_time
        current_time = datetime.datetime.now().timetuple()[:6]
        
        for name, data in dist_info_files:
            info = zipfile.ZipInfo(name, current_time)
            info.compress_type = zipfile.ZIP_DEFLATED

            # Handling a cross-platform edge case.
            pad_unix_permission_attrs_for_windows_compliance(info)
            file.writestr(info, data)



######## Entry point ########

def main() -> None:
    global meta_tag
    global pyproject
    
    pyproject = tomllib.loads((ROOT_DIRECTORY / "pyproject.toml").read_text(encoding="utf-8"))
    meta_tag = pyproject["project"]

    
    version: str = find_version_in_pyproject()
    dist_name: str = re.sub(r"[-_.]+", "_", meta_tag["name"])

    # The files to write to the wheel's .dist-info directory.
    dist_info_files: list[tuple[str, bytes]] = []

    # The wheel's .dist-info directory
    dist_info_subdir: str = f"{dist_name}-{version}.dist-info"
    
    # Creating 
    add_wheel_dist_info_subdir(dist_info_files, dist_info_subdir, version)
    
    wheel_file = DISTRIBUTION_DIRECTORY / f"{dist_name}-{version}-py3-none-any.whl"

    create_wheel_archive(dist_info_files, wheel_file)

    print(f"Built: {wheel_file} | Size: ({wheel_file.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    main()
