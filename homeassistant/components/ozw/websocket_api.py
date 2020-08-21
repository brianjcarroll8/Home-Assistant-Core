"""Web socket API for OpenZWave."""

import logging

from openzwavemqtt.const import EVENT_NODE_ADDED, EVENT_NODE_CHANGED
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import callback

from .const import DOMAIN, MANAGER, OPTIONS
from .migration import async_get_migration_data, async_migrate, map_node_values

_LOGGER = logging.getLogger(__name__)

TYPE = "type"
ID = "id"
OZW_INSTANCE = "ozw_instance"
NODE_ID = "node_id"
DRY_RUN = "dry_run"


@callback
def async_register_api(hass):
    """Register all of our api endpoints."""
    websocket_api.async_register_command(hass, websocket_migrate_zwave)
    websocket_api.async_register_command(hass, websocket_get_instances)
    websocket_api.async_register_command(hass, websocket_network_status)
    websocket_api.async_register_command(hass, websocket_node_metadata)
    websocket_api.async_register_command(hass, websocket_node_status)
    websocket_api.async_register_command(hass, websocket_node_statistics)
    websocket_api.async_register_command(hass, websocket_refresh_node_info)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "ozw/migrate_zwave",
        vol.Optional(DRY_RUN, default=True): vol.Coerce(bool),
    }
)
async def websocket_migrate_zwave(hass, connection, msg):
    """Migrate the zwave integration device and entity data to ozw integration."""
    if "zwave" not in hass.config.components:
        _LOGGER.error("Can not migrate, zwave integration is not loaded")
        connection.send_message(
            websocket_api.error_message(
                msg["id"], "zwave_not_loaded", "Integration zwave is not loaded"
            )
        )
        return

    zwave = hass.components.zwave
    zwave_data = await zwave.async_get_ozw_migration_data(hass)
    _LOGGER.debug("Migration zwave data: %s", zwave_data)

    ozw_data = await async_get_migration_data(hass)
    _LOGGER.debug("Migration ozw data: %s", ozw_data)

    can_migrate = map_node_values(zwave_data, ozw_data)

    zwave_entity_ids = [
        entry["entity_entry"].entity_id for entry in zwave_data.values()
    ]
    ozw_entity_ids = [entry["entity_entry"].entity_id for entry in ozw_data.values()]
    migration_entity_map = {
        zwave_entry["entity_entry"].entity_id: ozw_entity_id
        for ozw_entity_id, zwave_entry in can_migrate.items()
    }
    _LOGGER.debug("Migration entity map: %s", migration_entity_map)

    if not msg[DRY_RUN]:
        await async_migrate(hass, can_migrate)

    connection.send_result(
        msg[ID],
        {
            "zwave_entity_ids": zwave_entity_ids,
            "ozw_entity_ids": ozw_entity_ids,
            "migration_entity_map": migration_entity_map,
            "migrated": not msg[DRY_RUN],
        },
    )


@websocket_api.websocket_command({vol.Required(TYPE): "ozw/get_instances"})
def websocket_get_instances(hass, connection, msg):
    """Get a list of OZW instances."""
    manager = hass.data[DOMAIN][MANAGER]
    instances = []

    for instance in manager.collections["instance"]:
        instances.append(dict(instance.get_status().data, id=instance.id))

    connection.send_result(
        msg[ID], instances,
    )


@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "ozw/network_status",
        vol.Optional(OZW_INSTANCE, default=1): vol.Coerce(int),
    }
)
def websocket_network_status(hass, connection, msg):
    """Get Z-Wave network status."""

    manager = hass.data[DOMAIN][MANAGER]
    connection.send_result(
        msg[ID],
        {
            "state": manager.get_instance(msg[OZW_INSTANCE]).get_status().status,
            OZW_INSTANCE: msg[OZW_INSTANCE],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "ozw/node_status",
        vol.Required(NODE_ID): vol.Coerce(int),
        vol.Optional(OZW_INSTANCE, default=1): vol.Coerce(int),
    }
)
def websocket_node_status(hass, connection, msg):
    """Get the status for a Z-Wave node."""
    manager = hass.data[DOMAIN][MANAGER]
    node = manager.get_instance(msg[OZW_INSTANCE]).get_node(msg[NODE_ID])
    connection.send_result(
        msg[ID],
        {
            "node_query_stage": node.node_query_stage,
            "node_id": node.node_id,
            "is_zwave_plus": node.is_zwave_plus,
            "is_awake": node.is_awake,
            "is_failed": node.is_failed,
            "node_baud_rate": node.node_baud_rate,
            "is_beaming": node.is_beaming,
            "is_flirs": node.is_flirs,
            "is_routing": node.is_routing,
            "is_securityv1": node.is_securityv1,
            "node_basic_string": node.node_basic_string,
            "node_generic_string": node.node_generic_string,
            "node_specific_string": node.node_specific_string,
            "neighbors": node.neighbors,
            OZW_INSTANCE: msg[OZW_INSTANCE],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "ozw/node_metadata",
        vol.Required(NODE_ID): vol.Coerce(int),
        vol.Optional(OZW_INSTANCE, default=1): vol.Coerce(int),
    }
)
def websocket_node_metadata(hass, connection, msg):
    """Get the metadata for a Z-Wave node."""
    manager = hass.data[DOMAIN][MANAGER]
    node = manager.get_instance(msg[OZW_INSTANCE]).get_node(msg[NODE_ID])
    connection.send_result(
        msg[ID],
        {
            "metadata": node.meta_data,
            NODE_ID: node.node_id,
            OZW_INSTANCE: msg[OZW_INSTANCE],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "ozw/node_statistics",
        vol.Required(NODE_ID): vol.Coerce(int),
        vol.Optional(OZW_INSTANCE, default=1): vol.Coerce(int),
    }
)
def websocket_node_statistics(hass, connection, msg):
    """Get the statistics for a Z-Wave node."""
    manager = hass.data[DOMAIN][MANAGER]
    stats = (
        manager.get_instance(msg[OZW_INSTANCE]).get_node(msg[NODE_ID]).get_statistics()
    )
    connection.send_result(
        msg[ID],
        {
            "node_id": msg[NODE_ID],
            "send_count": stats.send_count,
            "sent_failed": stats.sent_failed,
            "retries": stats.retries,
            "last_request_rtt": stats.last_request_rtt,
            "last_response_rtt": stats.last_response_rtt,
            "average_request_rtt": stats.average_request_rtt,
            "average_response_rtt": stats.average_response_rtt,
            "received_packets": stats.received_packets,
            "received_dup_packets": stats.received_dup_packets,
            "received_unsolicited": stats.received_unsolicited,
            OZW_INSTANCE: msg[OZW_INSTANCE],
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "ozw/refresh_node_info",
        vol.Optional(OZW_INSTANCE, default=1): vol.Coerce(int),
        vol.Required(NODE_ID): vol.Coerce(int),
    }
)
def websocket_refresh_node_info(hass, connection, msg):
    """Tell OpenZWave to re-interview a node."""

    manager = hass.data[DOMAIN][MANAGER]
    options = hass.data[DOMAIN][OPTIONS]

    @callback
    def forward_node(node):
        """Forward node events to websocket."""
        if node.node_id != msg[NODE_ID]:
            return

        forward_data = {
            "type": "node_updated",
            "node_query_stage": node.node_query_stage,
        }
        connection.send_message(websocket_api.event_message(msg["id"], forward_data))

    @callback
    def async_cleanup() -> None:
        """Remove signal listeners."""
        for unsub in unsubs:
            unsub()

    connection.subscriptions[msg["id"]] = async_cleanup
    unsubs = [
        options.listen(EVENT_NODE_CHANGED, forward_node),
        options.listen(EVENT_NODE_ADDED, forward_node),
    ]

    instance = manager.get_instance(msg[OZW_INSTANCE])
    instance.refresh_node(msg[NODE_ID])
    connection.send_result(msg["id"])
