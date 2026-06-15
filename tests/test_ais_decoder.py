import pytest
from vf_core.message_bus import MessageBus

# The decoder plugin pulls in pyais; skip the whole module if it isn't installed.
ais_mod = pytest.importorskip("ais_decoder_processor")
AISDecoderProcessor = ais_mod.AISDecoderProcessor


@pytest.fixture
def processor():
    return AISDecoderProcessor(bus=MessageBus())


def test_position_report_is_dynamic_only(processor):
    decoded = {"msg_type": 1, "mmsi": 123456789, "lat": 53.4, "lon": -3.0, "speed": 12.3}
    msg = processor._normalise(decoded)
    assert msg is not None
    assert msg["identifier"] == "123456789"
    assert msg["source_type"] == "ais"
    assert msg["lat"] == 53.4
    assert msg["lon"] == -3.0
    assert msg["speed"] == 12.3
    assert "name" not in msg
    assert "extension" not in msg


def test_handled_fields_not_passed_through(processor):
    decoded = {"msg_type": 1, "mmsi": 123456789, "repeat": 0, "spare": 0, "lat": 1.0}
    msg = processor._normalise(decoded)
    for withdrawn in ("msg_type", "mmsi", "repeat", "spare"):
        assert withdrawn not in msg
    assert msg["lat"] == 1.0


@pytest.mark.parametrize("mmsi", ["12345678", "1234567890", "111234567"])
def test_invalid_mmsi_is_filtered(processor, mmsi):
    # Too short, too long, and SAR-aircraft (111...) MMSIs are all rejected.
    assert processor._normalise({"msg_type": 1, "mmsi": mmsi, "lat": 1.0}) is None


def test_type5_static_sets_name_and_extension(processor):
    decoded = {
        "msg_type": 5,
        "mmsi": 234567890,
        "shipname": "TEST VESSEL ",
        "callsign": "ABC123",
        "ship_type": 70,
        "imo": 9000001,
        "to_bow": 100,
        "to_stern": 20,
        "to_port": 5,
        "to_starboard": 6,
    }
    msg = processor._normalise(decoded)
    assert msg["identifier"] == "234567890"
    assert msg["name"] == "TEST VESSEL"  # whitespace stripped

    ext = msg["extension"]
    assert ext["callsign"] == "ABC123"
    assert ext["ship_type"] == 70
    assert ext["bow"] == 100
    assert ext["stern"] == 20
    assert "ship_type_name" in ext


def test_type24_part_a_sets_name_only(processor):
    decoded = {"msg_type": 24, "mmsi": 234567890, "part_num": 0, "shipname": "PART A"}
    msg = processor._normalise(decoded)
    assert msg["name"] == "PART A"
    assert "extension" not in msg


def test_type24_part_b_sets_extension(processor):
    decoded = {
        "msg_type": 24,
        "mmsi": 234567890,
        "part_num": 1,
        "callsign": "CS1",
        "ship_type": 60,
    }
    msg = processor._normalise(decoded)
    assert "name" not in msg
    ext = msg["extension"]
    assert ext["callsign"] == "CS1"
    assert ext["ship_type"] == 60
