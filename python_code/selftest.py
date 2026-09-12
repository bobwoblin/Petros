"""Offline Petros self-test. Performs no Discord or Arma network calls."""

import importlib.util
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("petros_core", HERE / "__init__.py")
PETROS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PETROS)


def server_frame(opcode, payload=b"", fin=True, masked=False, rsv=0):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    first = (0x80 if fin else 0) | rsv | opcode
    length = len(payload)
    mask_bit = 0x80 if masked else 0
    if length < 126:
        header = bytes((first, mask_bit | length))
    elif length <= 0xFFFF:
        header = bytes((first, mask_bit | 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, mask_bit | 127)) + struct.pack("!Q", length)
    if not masked:
        return header + payload
    key = b"\x01\x02\x03\x04"
    return header + key + PETROS._mask_payload(payload, key)


class FakeSocket:
    def __init__(self, data=b""):
        self.data = bytearray(data)
        self.sent = bytearray()

    def recv(self, size):
        if not self.data:
            return b""
        chunk = bytes(self.data[:size])
        del self.data[:size]
        return chunk

    def sendall(self, data):
        self.sent.extend(data)


class FakePresencePipe:
    def __init__(self, responses=b"", max_write=None):
        self.responses = bytearray(responses)
        self.writes = []
        self.closed = False
        self.max_write = max_write

    def read(self, size):
        if not self.responses:
            return b""
        chunk = bytes(self.responses[:size])
        del self.responses[:size]
        return chunk

    def write(self, data):
        data = bytes(data)
        if self.max_write is not None:
            data = data[:self.max_write]
        self.writes.append(data)
        return len(data)

    def close(self):
        self.closed = True


def decode_presence_frame(frame):
    opcode, size = struct.unpack("<II", frame[:8])
    return opcode, json.loads(frame[8:8 + size].decode("utf-8"))


class FakeRconSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.address = None
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def connect(self, address):
        self.address = address

    def send(self, data):
        self.sent.append(data)
        return len(data)

    def recv(self, size):
        if not self.responses:
            raise PETROS.socket.timeout()
        return self.responses.pop(0)

    def close(self):
        pass


def decode_client_frame(frame):
    first, second = frame[0], frame[1]
    assert second & 0x80
    pos = 2
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", frame[pos:pos + 2])[0]
        pos += 2
    elif length == 127:
        length = struct.unpack("!Q", frame[pos:pos + 8])[0]
        pos += 8
    key = frame[pos:pos + 4]
    pos += 4
    payload = PETROS._mask_payload(frame[pos:pos + length], key)
    return first & 0x0F, bool(first & 0x80), payload


class PetrosSelfTest(unittest.TestCase):
    def setUp(self):
        PETROS._mission_catalog = ()
        PETROS._presence_pipe = None
        PETROS._presence_application_id = ""
        PETROS._presence_started_at = 0
        self.cfg = dict(PETROS._DEFAULTS)
        self.cfg.update({
            "GUILD_ID": "100",
            "COMMAND_CHANNEL_ID": "200",
            "ADMIN_USER_IDS": {"1"},
            "ADMIN_ROLE_IDS": {"10"},
        })

    def interaction(self, command="status", user="2", roles=None, options=None, **overrides):
        value = {
            "type": 2,
            "id": "300",
            "token": "interaction-token",
            "guild_id": "100",
            "channel_id": "200",
            "member": {"user": {"id": user}, "roles": roles or []},
            "data": {"name": command, "options": options or []},
        }
        value.update(overrides)
        return value


    def test_rich_presence_ipc_payload(self):
        ready = PETROS._presence_frame(1, {"evt": "READY"})
        updated = PETROS._presence_frame(1, {"cmd": "SET_ACTIVITY", "data": {}})
        pipe = FakePresencePipe(ready + updated)
        with patch.object(PETROS, "_presence_open_pipe", return_value=pipe), \
                patch.object(PETROS.time, "time", return_value=1000.0), \
                patch.object(PETROS.time, "time_ns", return_value=1000000000):
            self.assertTrue(PETROS.update_presence(
                "123456789012345678",
                "Antistasi Ultimate",
                "Kujari • 3/8 players",
                3,
                8,
                "bobbys_junta",
                "Bobby's Junta",
            ))

        self.assertEqual(len(pipe.writes), 2)
        opcode, handshake = decode_presence_frame(pipe.writes[0])
        self.assertEqual(opcode, 0)
        self.assertEqual(handshake, {"v": 1, "client_id": "123456789012345678"})

        opcode, update = decode_presence_frame(pipe.writes[1])
        self.assertEqual(opcode, 1)
        activity = update["args"]["activity"]
        self.assertEqual(activity["details"], "Antistasi Ultimate")
        self.assertEqual(activity["state"], "Kujari • 3/8 players")
        self.assertEqual(activity["party"]["size"], [3, 8])
        self.assertEqual(activity["timestamps"]["start"], 1000)
        self.assertEqual(activity["assets"]["large_image"], "bobbys_junta")

    def test_rich_presence_rejects_invalid_application_id(self):
        self.assertFalse(PETROS.update_presence("not-an-id", "x", "y", 1, 8))

    def test_rich_presence_completes_partial_pipe_writes(self):
        pipe = FakePresencePipe(max_write=3)
        frame = PETROS._presence_frame(1, {"cmd": "SET_ACTIVITY"})
        PETROS._presence_write_all(pipe, frame)
        self.assertEqual(b"".join(pipe.writes), frame)
        self.assertGreater(len(pipe.writes), 1)

    def test_authorization_and_validation(self):
        ok, reason, parsed = PETROS._validate_interaction(self.interaction(), self.cfg)
        self.assertTrue(ok, reason)
        self.assertNotIn("user_id", parsed)
        ok, reason, _ = PETROS._validate_interaction(self.interaction(command="save", user="1"), self.cfg)
        self.assertTrue(ok, reason)
        ok, reason, _ = PETROS._validate_interaction(self.interaction(command="save", roles=["10"]), self.cfg)
        self.assertTrue(ok, reason)
        self.assertEqual(
            PETROS._validate_interaction(self.interaction(command="save"), self.cfg)[1],
            "unauthorized_management",
        )
        self.assertEqual(
            PETROS._validate_interaction(
                self.interaction(command="missionselect"), self.cfg
            )[1],
            "unauthorized_management",
        )
        self.assertEqual(PETROS._validate_interaction(self.interaction(guild_id="999"), self.cfg)[1], "wrong_guild")
        self.assertEqual(PETROS._validate_interaction(self.interaction(channel_id="999"), self.cfg)[1], "wrong_channel")
        self.assertEqual(PETROS._validate_interaction(self.interaction(token=""), self.cfg)[1], "missing_token")

    def test_typed_options(self):
        good_location = [{"name": "type", "type": 3, "value": "airports"}]
        ok, _, parsed = PETROS._validate_options("locations", good_location)
        self.assertTrue(ok)
        self.assertEqual(parsed, ["airports"])
        self.assertFalse(PETROS._validate_options("locations", [{"name": "type", "type": 3, "value": "secret"}])[0])
        self.assertTrue(
            PETROS._validate_options(
                "announce",
                [{"name": "message", "type": 3, "value": "Server restart soon"}],
            )[0]
        )
        self.assertFalse(
            PETROS._validate_options(
                "announce", [{"name": "message", "type": 3, "value": "bad\nline"}]
            )[0]
        )
        self.assertFalse(
            PETROS._validate_options(
                "announce",
                [{"name": "message", "type": 3, "value": "<t>formatted</t>"}],
            )[0]
        )
        self.assertTrue(
            PETROS._validate_options(
                "loadmission",
                [
                    {
                        "name": "mission",
                        "type": 3,
                        "value": "Antistasi_tem_kujari.tem_kujari",
                    }
                ],
            )[0]
        )
        self.assertFalse(
            PETROS._validate_options(
                "loadmission",
                [{"name": "mission", "type": 3, "value": "x;#shutdown"}],
            )[0]
        )
        self.assertTrue(PETROS._validate_options("loadsave", [{"name": "id", "type": 3, "value": "12345"}])[0])
        self.assertFalse(PETROS._validate_options("loadsave", [{"name": "id", "type": 3, "value": "bad id"}])[0])

    def test_battleye_rcon_packets_and_fragmentation(self):
        login = PETROS._rcon_packet(b"\xff\x00\x01")
        notice = PETROS._rcon_packet(b"\xff\x02\x07notice")
        part0 = PETROS._rcon_packet(b"\xff\x01\x00\x00\x02\x00first ")
        part1 = PETROS._rcon_packet(b"\xff\x01\x00\x00\x02\x01second")
        fake = FakeRconSocket([login, notice, part0, part1])
        with patch.dict(PETROS._config, {"RCON_PORT": 2301, "RCON_PASSWORD": "secret"}), \
                patch.object(PETROS.socket, "socket", return_value=fake):
            self.assertEqual(PETROS._rcon_command("#mpmissions"), "first second")
            self.assertEqual(fake.address, ("127.0.0.1", 2301))
            packet_type, payload = PETROS._rcon_parse(fake.sent[0])
            self.assertEqual((packet_type, payload), (0, b"secret"))
            packet_type, payload = PETROS._rcon_parse(fake.sent[1])
            self.assertEqual((packet_type, payload), (1, b"\x00#mpmissions"))
            packet_type, payload = PETROS._rcon_parse(fake.sent[2])
            self.assertEqual((packet_type, payload), (2, b"\x07"))


    def test_mpmissions_collects_raw_server_messages(self):
        login = PETROS._rcon_packet(b"\xff\x00\x01")
        connected = PETROS._rcon_packet(b"\xff\x02\x01Player #0 SERVER connected")
        path = PETROS._rcon_packet(b"\xff\x02\x02custom\\example\\mpmissions\\")
        mission1 = PETROS._rcon_packet(b"\xff\x02\x03Antistasi_tem_kujari.tem_kujari")
        mission2 = PETROS._rcon_packet(b"\xff\x02\x04TestMission.Altis")
        disconnected = PETROS._rcon_packet(b"\xff\x02\x05Player #0 SERVER disconnected")
        fake = FakeRconSocket([login, connected, path, mission1, mission2, disconnected])
        with patch.dict(PETROS._config, {"RCON_PORT": 2301, "RCON_PASSWORD": "secret"}), \
                patch.object(PETROS.socket, "socket", return_value=fake):
            output = PETROS._rcon_command("#mpmissions", capture_command_messages=True)
            self.assertEqual(
                PETROS._mission_templates(output),
                ["Antistasi_tem_kujari.tem_kujari", "TestMission.Altis"],
            )
            ack_payloads = [PETROS._rcon_parse(packet) for packet in fake.sent[2:]]
            self.assertEqual(
                [payload for kind, payload in ack_payloads if kind == 2],
                [b"\x01", b"\x02", b"\x03", b"\x04", b"\x05"],
            )

    def test_mission_templates_accepts_display_prefixes(self):
        output = "\n".join((
            "(Command) SERVER: custom\\example\\mpmissions\\",
            "(Command) SERVER: Antistasi_tem_kujari.tem_kujari",
            "SERVER: TestMission.Altis",
            "Player #0 SERVER (127.0.0.1:2302) connected",
        ))
        self.assertEqual(
            PETROS._mission_templates(output),
            ["Antistasi_tem_kujari.tem_kujari", "TestMission.Altis"],
        )

    def test_servermissions_combines_rcon_and_cfgmissions(self):
        calls = []
        PETROS.set_missions(["Antistasi_tem_kujari.tem_kujari"])
        def fake(command, capture_command_messages=False):
            calls.append((command, capture_command_messages))
            return "" if command == "#mpmissions" else "Missions on server:\nTestMission.Altis.pbo"
        with patch.object(PETROS, "_rcon_command", side_effect=fake):
            payload = PETROS._run_server_command("servermissions", [])
        self.assertEqual(calls, [("#mpmissions", True), ("missions", False)])
        description = payload["embeds"][0]["description"]
        self.assertIn("TestMission.Altis", description)
        self.assertIn("Antistasi_tem_kujari.tem_kujari", description)

    def test_cfgmissions_survives_rcon_listing_failure(self):
        PETROS.set_missions(["Antistasi_tem_kujari.tem_kujari", "bad", "Antistasi_tem_kujari.tem_kujari"])
        with patch.object(PETROS, "_rcon_command", side_effect=RuntimeError("RCon failed")):
            self.assertEqual(PETROS._available_missions(), ["Antistasi_tem_kujari.tem_kujari"])

    def test_fixed_server_commands(self):
        with patch.object(PETROS, "_rcon_command", side_effect=["restarting", "selecting"]) as rcon:
            restart = PETROS._run_server_command("restartmission", [])
            select = PETROS._run_server_command("missionselect", [])
        self.assertEqual([call.args[0] for call in rcon.call_args_list], ["#restart", "#missions"])
        self.assertIn("restarting", restart["embeds"][0]["description"])
        self.assertIn("selecting", select["embeds"][0]["description"])

    def test_websocket_accept(self):
        self.assertEqual(
            PETROS._ws_accept("dGhlIHNhbXBsZSBub25jZQ=="),
            "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        )

    def test_client_masking_and_lengths(self):
        key = b"\x37\xfa\x21\x3d"
        for size in (0, 1, 125, 126, 65535, 65536):
            payload = bytes((i % 251 for i in range(size)))
            frame = PETROS._ws_frame(1, payload, mask_key=key)
            opcode, fin, decoded = decode_client_frame(frame)
            self.assertEqual(opcode, 1)
            self.assertTrue(fin)
            self.assertEqual(decoded, payload)
            self.assertTrue(frame[1] & 0x80)

    def test_fragmentation_and_handshake_leftover_buffer(self):
        data = server_frame(1, "hel", fin=False) + server_frame(0, "lo", fin=True)
        sock = FakeSocket()
        buffer = bytearray(data)
        self.assertEqual(PETROS._ws_recv_message(sock, buffer), "hello")
        self.assertEqual(buffer, bytearray())

    def test_ping_pong(self):
        sock = FakeSocket(server_frame(9, b"abc") + server_frame(1, "ok"))
        self.assertEqual(PETROS._ws_recv_message(sock, bytearray()), "ok")
        opcode, fin, payload = decode_client_frame(bytes(sock.sent))
        self.assertEqual((opcode, fin, payload), (10, True, b"abc"))

    def test_close(self):
        payload = struct.pack("!H", 1000) + b"bye"
        sock = FakeSocket(server_frame(8, payload))
        with self.assertRaises(PETROS._WsClosed) as caught:
            PETROS._ws_recv_message(sock, bytearray())
        self.assertEqual(caught.exception.code, 1000)
        opcode, fin, echoed = decode_client_frame(bytes(sock.sent))
        self.assertEqual((opcode, fin, echoed), (8, True, payload))

    def test_rejects_masked_rsv_and_reserved_server_frames(self):
        for data in (
            server_frame(1, "bad", masked=True),
            server_frame(1, "bad", rsv=0x40),
            server_frame(0xB, b""),
        ):
            with self.assertRaises(PETROS._WsClosed) as caught:
                PETROS._ws_recv_message(FakeSocket(data), bytearray())
            self.assertEqual(caught.exception.code, 1002)

    def test_embed_limits(self):
        fields = [["n" * 400, "v" * 1500, True] for _ in range(30)]
        embed = PETROS._make_embed("t" * 400, "d" * 6000, fields)
        self.assertLessEqual(len(embed["title"]), 256)
        self.assertLessEqual(len(embed["description"]), 4096)
        self.assertLessEqual(len(embed["fields"]), 25)
        total = (
            len(embed["title"])
            + len(embed["description"])
            + len(embed["author"]["name"])
            + len(embed["footer"]["text"])
        )
        for field in embed["fields"]:
            self.assertLessEqual(len(field["name"]), 256)
            self.assertLessEqual(len(field["value"]), 1024)
            total += len(field["name"]) + len(field["value"])
        self.assertLessEqual(total, 6000)

    def test_event_embed_uses_editable_presentation(self):
        presentation = {
            "EMBED": dict(PETROS._PRESENTATION_DEFAULTS["EMBED"]),
            "COLORS": dict(PETROS._PRESENTATION_DEFAULTS["COLORS"]),
            "EVENTS": {
                "player_join": {
                    "title": "Joined",
                    "description": "**{player}** arrived.",
                    "color": 12345,
                }
            },
        }
        config = dict(PETROS._DEFAULTS)
        config.update({"EVENT_CHANNEL_ID": "200", "NOTIFY_PLAYER_JOINS": True})
        queued = []
        with patch.object(PETROS, "_presentation", presentation), \
                patch.object(PETROS, "_config", config), \
                patch.object(PETROS, "_enqueue_out", side_effect=lambda item, high=False: queued.append(item) or True):
            self.assertTrue(PETROS.send_event("player_join", "Austin joined.", [["Player", "Austin", True]]))
        embed = queued[0]["payload"]["embeds"][0]
        self.assertEqual(embed["title"], "Joined")
        self.assertEqual(embed["description"], "**Austin** arrived.")
        self.assertEqual(embed["color"], 12345)

    def test_rest_startup_recovers_after_transient_failure(self):
        calls = []
        sleeps = []

        def fake_request(method, path, *args, **kwargs):
            calls.append((method, path))
            if len(calls) == 1:
                raise RuntimeError("Discord HTTP 429")
            if path == "/users/@me":
                return {"id": "1"}
            return None

        stop = lambda *args, **kwargs: (_ for _ in ()).throw(StopIteration())
        with patch.object(PETROS, "_commands_ready", False), \
                patch.object(PETROS, "_rest_ready", False), \
                patch.dict(PETROS._config, {"APPLICATION_ID": "123", "GUILD_ID": "456"}), \
                patch.object(PETROS, "_rest_request", side_effect=fake_request), \
                patch.object(PETROS.time, "sleep", side_effect=sleeps.append), \
                patch.object(PETROS._out_event, "wait", side_effect=stop):
            with self.assertRaises(StopIteration):
                PETROS._rest_worker()
            self.assertTrue(PETROS._rest_ready)
            self.assertTrue(PETROS._commands_ready)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(
            calls[:3],
            [
                ("GET", "/users/@me"),
                ("GET", "/users/@me"),
                ("PUT", "/applications/123/guilds/456/commands"),
            ],
        )

    def test_immediate_response_helper(self):
        calls = []
        with patch.object(PETROS, "_callback", side_effect=lambda *args: calls.append(args)):
            PETROS._respond({"id": "1", "token": "token"}, "ok", True)
        self.assertEqual(calls[0][0:2], ("1", "token"))
        self.assertEqual(calls[0][2]["data"]["flags"], 64)

    def test_command_registration_shape(self):
        commands = PETROS._commands_payload()
        self.assertEqual({command["name"] for command in commands}, PETROS.ALL_COMMANDS)
        locations = next(command for command in commands if command["name"] == "locations")
        self.assertEqual(
            {choice["value"] for choice in locations["options"][0]["choices"]},
            PETROS.LOCATION_VALUES,
        )
        self.assertTrue(all("integration_types" not in command and "contexts" not in command for command in commands))

    def test_no_extra_runtime_dependencies(self):
        source = (HERE / "__init__.py").read_text(encoding="utf-8")
        forbidden = ("discord.py", "import requests", "import websocket", "import aiohttp")
        self.assertFalse(any(item in source for item in forbidden))


if __name__ == "__main__":
    unittest.main(verbosity=2)
