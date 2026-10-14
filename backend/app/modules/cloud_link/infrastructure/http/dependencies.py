from typing import Annotated

from fastapi import Depends

from app.modules.cloud_link.infrastructure.composition import (
    CloudLinkServices,
    get_cloud_link_services,
)

CloudLinkServicesDep = Annotated[CloudLinkServices, Depends(get_cloud_link_services)]
