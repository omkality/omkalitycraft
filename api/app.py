from litestar import Litestar
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.openapi import OpenAPIConfig

from api.core.project import get_project_info
from api.lifecycle import report_retention
from api.routes.download import download_instance_file, download_launcher_file
from api.routes.instances import (
    get_instance_config,
    get_instance_manifest,
    get_launch_profile,
    list_instances,
)
from api.routes.launcher import get_launcher_manifest
from api.routes.meta import docs_redirect, health, version
from api.routes.releases import get_release_file, get_release_manifest
from api.routes.reports import upload_client_report
from api.routes.updates import update_metadata, update_target

project_info = get_project_info()


def create_app(requests_per_second: int = 128) -> Litestar:
    return Litestar(
        lifespan=[report_retention],
        middleware=[
            RateLimitConfig(rate_limit=("second", requests_per_second)).middleware
        ],
        route_handlers=[
            upload_client_report,
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
            get_release_manifest,
            get_release_file,
            update_metadata,
            update_target,
        ],
        openapi_config=OpenAPIConfig(
            title="OmkalityCraft CDN API",
            version=project_info["version"],
            description=project_info["description"],
            path="/docs",
        ),
    )


app = create_app()
