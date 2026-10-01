#!/usr/bin/env python3
"""Apply lab additions without replacing current upstream lifecycle/resources."""
import argparse
import copy
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ANDROID = "{http://schemas.android.com/apk/res/android}"
ET.register_namespace("android", ANDROID[1:-1])
ET.register_namespace("tools", "http://schemas.android.com/tools")
APP = Path("app/src/main/java/com/fongmi/android/tv/App.java")
MANIFEST = Path("app/src/main/AndroidManifest.xml")


def parse_xml(data):
    return ET.fromstring(data, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))


def write_xml(path, root):
    ET.indent(root, space="    ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def merge_values(current, overlay):
    if current.tag != "resources" or overlay.tag != "resources":
        raise ValueError("Expected Android resources XML")
    def key(element):
        return element.get("type", element.tag), element.get("name")
    entries = {key(e): e for e in current if isinstance(e.tag, str) and e.get("name")}
    for element in overlay:
        if not isinstance(element.tag, str) or not element.get("name"):
            continue
        previous = entries.get(key(element))
        replacement = copy.deepcopy(element)
        if previous is not None:
            current.remove(previous)
        current.append(replacement)
        entries[key(element)] = replacement
    return current


def manifest_key(element):
    if element.tag in ("application", "queries"):
        return element.tag,
    name = element.get(ANDROID + "name")
    if name is not None:
        return element.tag, name
    return element.tag, tuple(sorted(element.attrib.items())), tuple(
        manifest_key(child) for child in element if isinstance(child.tag, str))


def merge_manifest(current, overlay):
    # Upstream owns existing components and attributes. Add lab-only components
    # and package/intent queries while retaining new upstream pages and services.
    entries = {manifest_key(e): e for e in current if isinstance(e.tag, str)}
    for element in overlay:
        if not isinstance(element.tag, str):
            continue
        previous = entries.get(manifest_key(element))
        if previous is None:
            added = copy.deepcopy(element)
            current.append(added)
            entries[manifest_key(element)] = added
        elif element.tag in ("application", "queries"):
            merge_manifest(previous, element)
    return current


def apply_overlay(archive, source):
    source = Path(source).resolve()
    app_path = source / APP
    original_app = app_path.read_bytes()
    copied = merged = 0
    with ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            if entry.is_dir():
                continue
            target = (source / entry.filename).resolve()
            if not target.is_relative_to(source):
                raise ValueError(f"Overlay path escapes source directory: {entry.filename}")
            if target == app_path:
                continue
            data = bundle.read(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target == source / MANIFEST:
                write_xml(target, merge_manifest(parse_xml(target.read_bytes()), parse_xml(data)))
                merged += 1
            elif target.exists() and target.suffix == ".xml" and target.parent.name.startswith("values"):
                write_xml(target, merge_values(parse_xml(target.read_bytes()), parse_xml(data)))
                merged += 1
            else:
                target.write_bytes(data)
                copied += 1
    if app_path.read_bytes() != original_app:
        raise RuntimeError("Upstream App.java was unexpectedly replaced")
    print(f"Preserved upstream App.java; merged {merged} XML files; copied {copied} lab files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    apply_overlay(args.archive, args.source)
