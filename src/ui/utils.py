#!/usr/bin/python3

from os.path import join
from typing import List, Optional


def path_to_dict(
    path: str,
    *,
    is_cache: bool = False,
    db_data: Optional[List[dict]] = None,
    services: Optional[List[dict]] = None,
) -> dict:
    db_data = db_data or []
    services = services or []

    if not is_cache:
        config_types = [
            "http",
            "stream",
            "server-http",
            "server-stream",
            "default-server-http",
            "modsec",
            "modsec-crs",
        ]

        d = {
            "name": "configs",
            "type": "folder",
            "path": path,
            "can_create_files": False,
            "can_create_folders": False,
            "can_edit": False,
            "can_delete": False,
            "children": [
                {
                    "name": config,
                    "type": "folder",
                    "path": join(path, config),
                    "can_create_files": True,
                    "can_create_folders": False,
                    "can_edit": False,
                    "can_delete": False,
                    "children": [
                        {
                            "name": service,
                            "type": "folder",
                            "path": join(path, config, service),
                            "can_create_files": True,
                            "can_create_folders": False,
                            "can_edit": False,
                            "can_delete": False,
                            "children": [],
                        }
                        for service in services
                    ],
                }
                for config in config_types
            ],
        }

        for conf in db_data:
            type_lower = conf["type"].replace("_", "-")
            file_info = {
                "name": f"{conf['name']}.conf",
                "type": "file",
                "path": join(
                    path,
                    type_lower,
                    conf["service_id"] if conf["service_id"] else "",
                    f"{conf['name']}.conf",
                ),
                "can_edit": conf["method"] == "ui",
                "can_delete": True,
                "can_download": True,
                "content": conf["data"].decode("utf-8"),
            }

            if conf["service_id"]:
                d["children"][config_types.index(type_lower)]["children"][
                    [
                        x["name"]
                        for x in d["children"][config_types.index(type_lower)][
                            "children"
                        ]
                    ].index(conf["service_id"])
                ]["children"].append(file_info)
            else:
                d["children"][config_types.index(type_lower)]["children"].append(
                    file_info
                )
    else:
        d = {
            "name": "cache",
            "type": "folder",
            "path": path,
            "can_create_files": False,
            "can_create_folders": False,
            "can_edit": False,
            "can_delete": False,
            "children": [
                {
                    "name": service,
                    "type": "folder",
                    "path": join(path, service),
                    "can_create_files": False,
                    "can_create_folders": False,
                    "can_edit": False,
                    "can_delete": False,
                    "children": [],
                }
                for service in services
            ],
        }

        for conf in db_data:
            file_info = {
                "name": join(conf["job_name"], conf["file_name"]),
                "type": "file",
                "path": join(
                    path,
                    conf["service_id"] if conf["service_id"] else "",
                    conf["file_name"],
                ),
                "can_edit": False,
                "can_delete": False,
                "can_download": True,
                "content": conf["data"],
            }

            if conf["service_id"]:
                d["children"][
                    [x["name"] for x in d["children"]].index(conf["service_id"])
                ]["children"].append(file_info)
            else:
                d["children"].append(file_info)

    return d


def check_settings(settings: dict, check: str) -> bool:
    return any(setting["context"] == check for setting in settings.values())
