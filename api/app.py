from litestar import Litestar
from litestar.openapi import OpenAPIConfig

from api.core.project import get_project_info
from api.routes.download import download_instance_file, download_launcher_file
from api.routes.instances import (
    get_instance_config,
    get_instance_manifest,
    get_launch_profile,
    list_instances,
)
from api.routes.launcher import get_launcher_manifest
from api.routes.meta import docs_redirect, health, version

project_info = get_project_info()

app = Litestar(
    route_handlers=[
        docs_redirect,
        version,
        health,
        get_launcher_manifest,
        list_instances,
        get_instance_manifest,
        get_instance_config,
        get_launch_profile,
        download_launcher_file,
        download_instance_file,
    ],
    openapi_config=OpenAPIConfig(
        title="OmkalityCraft CDN API",
        version=project_info["version"],
        description=project_info["description"],
        path="/docs",
    ),
)
