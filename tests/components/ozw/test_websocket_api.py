"""Test OpenZWave Websocket API."""
import pytest

from homeassistant.components.ozw.websocket_api import ID, NODE_ID, OZW_INSTANCE, TYPE
from homeassistant.helpers.entity_registry import RegistryEntry

from .common import MQTTMessage, setup_ozw

from tests.async_mock import AsyncMock, patch
from tests.common import MockModule, mock_integration


@pytest.fixture(name="zwave_migration_data")
def zwave_migration_data_fixture():
    """Return mock zwave migration data."""
    zwave_source_node_unique_id = "10-4321"
    zwave_source_node_entry = RegistryEntry(
        entity_id="sensor.zwave_source_node",
        unique_id=zwave_source_node_unique_id,
        platform="zwave",
        name="Z-Wave Source Node",
    )
    zwave_battery_unique_id = "36-1234"
    zwave_battery_entry = RegistryEntry(
        entity_id="sensor.zwave_battery_level",
        unique_id=zwave_battery_unique_id,
        platform="zwave",
        name="Z-Wave Battery Level",
    )
    zwave_power_unique_id = "32-5678"
    zwave_power_entry = RegistryEntry(
        entity_id="sensor.zwave_power",
        unique_id=zwave_power_unique_id,
        platform="zwave",
        name="Z-Wave Power",
    )
    zwave_migration_data = {
        zwave_source_node_unique_id: {
            "node_id": 10,
            "command_class": 113,
            "command_class_label": "SourceNodeId",
            "value_index": 2,
            "unique_id": zwave_source_node_unique_id,
            "entity_entry": zwave_source_node_entry,
        },
        zwave_battery_unique_id: {
            "node_id": 36,
            "command_class": 128,
            "command_class_label": "Battery Level",
            "value_index": 0,
            "unique_id": zwave_battery_unique_id,
            "entity_entry": zwave_battery_entry,
        },
        zwave_power_unique_id: {
            "node_id": 32,
            "command_class": 50,
            "command_class_label": "Power",
            "value_index": 8,
            "unique_id": zwave_power_unique_id,
            "entity_entry": zwave_power_entry,
        },
    }

    return zwave_migration_data


@pytest.fixture(name="zwave_integration")
def zwave_integration_fixture(hass, zwave_migration_data):
    """Mock the zwave integration."""
    zwave_module = MockModule("zwave")
    zwave_module.async_get_ozw_migration_data = AsyncMock(
        return_value=zwave_migration_data
    )
    zwave_integration = mock_integration(hass, zwave_module)
    hass.config.components.add("zwave")
    return zwave_integration


async def test_migrate_zwave(
    hass, migration_data, hass_ws_client, zwave_integration, zwave_migration_data
):
    """Test the zwave to ozw migration websocket api."""
    await setup_ozw(hass, fixture=migration_data)
    client = await hass_ws_client(hass)

    await client.send_json({ID: 5, TYPE: "ozw/migrate_zwave"})
    msg = await client.receive_json()
    result = msg["result"]

    migration_entity_map = {
        "sensor.zwave_battery_level": "sensor.water_sensor_6_battery_level",
        "sensor.zwave_power": "sensor.smart_plug_electric_w",
    }

    assert result["zwave_entity_ids"] == [
        "sensor.zwave_source_node",
        "sensor.zwave_battery_level",
        "sensor.zwave_power",
    ]
    assert result["ozw_entity_ids"] == [
        "sensor.smart_plug_electric_w",
        "sensor.water_sensor_6_battery_level",
    ]
    assert result["migration_entity_map"] == migration_entity_map
    assert result["migrated"] is False


async def test_websocket_api(hass, generic_data, hass_ws_client):
    """Test the ozw websocket api."""
    await setup_ozw(hass, fixture=generic_data)
    client = await hass_ws_client(hass)

    # Test instance list
    await client.send_json({ID: 4, TYPE: "ozw/get_instances"})
    msg = await client.receive_json()
    assert len(msg["result"]) == 1
    result = msg["result"][0]
    assert result["id"] == 1
    assert result["Status"] == "driverAllNodesQueried"
    assert result["OpenZWave_Version"] == "1.6.1008"

    # Test network status
    await client.send_json({ID: 5, TYPE: "ozw/network_status"})
    msg = await client.receive_json()
    result = msg["result"]

    assert result["state"] == "driverAllNodesQueried"
    assert result[OZW_INSTANCE] == 1

    # Test node status
    await client.send_json({ID: 6, TYPE: "ozw/node_status", NODE_ID: 32})
    msg = await client.receive_json()
    result = msg["result"]

    assert result[OZW_INSTANCE] == 1
    assert result[NODE_ID] == 32
    assert result["node_query_stage"] == "Complete"
    assert result["is_zwave_plus"]
    assert result["is_awake"]
    assert not result["is_failed"]
    assert result["node_baud_rate"] == 100000
    assert result["is_beaming"]
    assert not result["is_flirs"]
    assert result["is_routing"]
    assert not result["is_securityv1"]
    assert result["node_basic_string"] == "Routing Slave"
    assert result["node_generic_string"] == "Binary Switch"
    assert result["node_specific_string"] == "Binary Power Switch"
    assert result["neighbors"] == [1, 33, 36, 37, 39]

    # Test node statistics
    await client.send_json({ID: 7, TYPE: "ozw/node_statistics", NODE_ID: 39})
    msg = await client.receive_json()
    result = msg["result"]

    assert result[OZW_INSTANCE] == 1
    assert result[NODE_ID] == 39
    assert result["send_count"] == 57
    assert result["sent_failed"] == 0
    assert result["retries"] == 1
    assert result["last_request_rtt"] == 26
    assert result["last_response_rtt"] == 38
    assert result["average_request_rtt"] == 29
    assert result["average_response_rtt"] == 37
    assert result["received_packets"] == 3594
    assert result["received_dup_packets"] == 12
    assert result["received_unsolicited"] == 3546

    # Test node metadata
    await client.send_json({ID: 8, TYPE: "ozw/node_metadata", NODE_ID: 39})
    msg = await client.receive_json()
    result = msg["result"]
    assert result["metadata"]["ProductPic"] == "images/aeotec/zwa002.png"


async def test_refresh_node(hass, generic_data, sent_messages, hass_ws_client):
    """Test the ozw refresh node api."""
    receive_message = await setup_ozw(hass, fixture=generic_data)
    client = await hass_ws_client(hass)

    # Send the refresh_node_info command
    await client.send_json({ID: 9, TYPE: "ozw/refresh_node_info", NODE_ID: 39})
    msg = await client.receive_json()

    assert len(sent_messages) == 1
    assert msg["success"]

    # Receive a mock status update from OZW
    message = MQTTMessage(
        topic="OpenZWave/1/node/39/",
        payload={"NodeID": 39, "NodeQueryStage": "initializing"},
    )
    message.encode()
    receive_message(message)

    # Verify we got expected data on the websocket
    msg = await client.receive_json()
    result = msg["event"]
    assert result["type"] == "node_updated"
    assert result["node_query_stage"] == "initializing"

    # Send another mock status update from OZW
    message = MQTTMessage(
        topic="OpenZWave/1/node/39/",
        payload={"NodeID": 39, "NodeQueryStage": "versions"},
    )
    message.encode()
    receive_message(message)

    # Send a mock status update for a different node
    message = MQTTMessage(
        topic="OpenZWave/1/node/35/",
        payload={"NodeID": 35, "NodeQueryStage": "fake_shouldnt_be_received"},
    )
    message.encode()
    receive_message(message)

    # Verify we received the message for node 39 but not for node 35
    msg = await client.receive_json()
    result = msg["event"]
    assert result["type"] == "node_updated"
    assert result["node_query_stage"] == "versions"


async def test_refresh_node_unsubscribe(hass, generic_data, hass_ws_client):
    """Test unsubscribing the ozw refresh node api."""
    await setup_ozw(hass, fixture=generic_data)
    client = await hass_ws_client(hass)

    with patch("openzwavemqtt.OZWOptions.listen") as mock_listen:
        # Send the refresh_node_info command
        await client.send_json({ID: 9, TYPE: "ozw/refresh_node_info", NODE_ID: 39})
        await client.receive_json()

        # Send the unsubscribe command
        await client.send_json({ID: 10, TYPE: "unsubscribe_events", "subscription": 9})
        await client.receive_json()

        assert mock_listen.return_value.called
