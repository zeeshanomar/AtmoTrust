import asyncio
import hashlib
import secrets
from fastapi.testclient import TestClient
from app.controller import RunController
from app.data import PreparedSource
from app.main import app, controller as app_controller
from app.schema import Assessment, Command, Injection, InjectionSpec, SourceStatus
from app.simulation import ScenarioInjector
from app.health import HealthEngine


def controller(tmp_path):
    return RunController(database_path=tmp_path / "test.sqlite3")


def test_data_package():
    source = PreparedSource()
    assert source.total_frames >= 100
    assert source.manifest["rows"] == source.total_frames * 15
    assert source.manifest["pressure_reference"] == "mean_sea_level"
    assert all(len(source.read_frame(i)) == 15 for i in (0, source.total_frames // 2, source.total_frames - 1))
    assert all(item.source_name == source.manifest["source_name"] for item in source.read_frame(0))
    assert all(hashlib.sha256((source.data_dir / filename).read_bytes()).hexdigest() == digest for filename, digest in source.manifest["hashes"].items())


def test_model_safe_projection_excludes_truth():
    item = PreparedSource().read_frame(0)[0]
    item.is_test_overlay = True
    item.raw_value = -999
    assert set(item.model_input()) == {"sample_id", "station_id", "variable", "value", "timestamp", "sequence"}
    assert "-999" not in str(item.model_input())


def test_health_requires_context():
    assessment = Assessment(sample_id="x", station_id="CHD-01", variable="temperature_c", timestamp="2026-08-01T00:00:00Z", assessment_status="insufficient_context")
    item = HealthEngine().update([assessment], {}, [])[0]
    assert item.health_score is None and item.health_status == "unknown"


def test_fault_transforms_deterministic():
    from app.schema import Injection
    source = PreparedSource()
    frame = source.read_frame(10)
    base = next(o for o in frame if o.station_id == "CHD-01" and o.variable == "temperature_c")
    prior = source.read_frame(9)[0].value
    for fault in ("spike", "freeze", "drift", "bias", "noise", "missing"):
        injection = Injection(station_id="CHD-01", variable="temperature_c", fault_type=fault, magnitude=8, duration_samples=3, injection_id="x", start_sequence=10, end_sequence=13)
        first = ScenarioInjector().apply(frame, [injection], None, 10, {("CHD-01", "temperature_c"): prior})[0]
        second = ScenarioInjector().apply(frame, [injection], None, 10, {("CHD-01", "temperature_c"): prior})[0]
        assert first.value == second.value
        assert first.raw_value == base.value
        assert first.is_test_overlay
        assert first.value != base.value or fault == "freeze" and prior == base.value
        if fault == "noise":
            changed_id = injection.model_copy(update={"injection_id": "another-id"})
            assert ScenarioInjector().apply(frame, [changed_id], None, 10)[0].value == first.value


def test_spike_incident_actions_and_reset(tmp_path):
    c = controller(tmp_path)
    async def run():
        await c.inject([InjectionSpec(station_id="CHD-01", variable="temperature_c", fault_type="spike", magnitude=9, duration_samples=3)])
        state = await c.step()
        target = next(a for a in state.latest_assessments if a.station_id == "CHD-01" and a.variable == "temperature_c")
        assert target.decision == "likely_fault", target
        assert target.fault_type == "spike"
        assert target.evidence and target.trust_score is not None
        assert state.maintenance_items
        await c.act(state.maintenance_items[0].incident_id, "acknowledge")
        assert c.actions[-1].action == "acknowledge"
        generation = c.generation
        reset = await c.command(Command(command="reset"))
        assert reset.generation == generation + 1
        assert not reset.active_injections and not reset.active_incidents
        assert sum(a.decision == "likely_genuine" for a in reset.latest_assessments) >= 12
        assert all(a.decision != "likely_fault" for a in reset.latest_assessments)
    asyncio.run(run())


def test_batch_missing_regional_compound(tmp_path):
    c = controller(tmp_path)
    async def run():
        await c.inject([InjectionSpec(station_id="CHD-01", variable="temperature_c", fault_type="missing", magnitude=0, duration_samples=2), InjectionSpec(station_id="MOH-01", variable="humidity_pct", fault_type="bias", magnitude=30, duration_samples=2)])
        first = await c.step()
        assert len({i.start_sequence for i in c.injections}) == 1
        missing = next(a for a in first.latest_assessments if a.station_id == "CHD-01" and a.variable == "temperature_c")
        assert missing.assessment_status == "missing" and missing.trust_score is None
        assert next(o for o in first.recent_observations if o.sample_id == missing.sample_id).value is None
        active = next(i for i in first.active_injections if i.status == "active")
        await c.cancel(active.injection_id)
        assert active.status == "cancelled" and active.remaining_samples == 0
        recovered = await c.step()
        assert next(o for o in recovered.recent_observations if o.sequence == recovered.sequence and o.station_id == "CHD-01" and o.variable == "temperature_c").value is not None
        await c.command(Command(command="reset"))
        await c.regional(12)
        await c.inject([InjectionSpec(station_id="CHD-01", variable="temperature_c", fault_type="spike", magnitude=9, duration_samples=3)])
        compound = await c.step()
        temps = [a for a in compound.latest_assessments if a.variable == "temperature_c"]
        assert next(a for a in temps if a.station_id == "CHD-01").decision == "likely_fault"
        assert sum(a.decision == "likely_fault" for a in temps) == 1
        assert all(a.assessment_status != "invalid" for a in compound.latest_assessments)
    asyncio.run(run())


def test_api_and_two_websocket_clients():
    with TestClient(app) as client:
        username, password = f"test_{secrets.token_hex(6)}", secrets.token_urlsafe(20)
        app_controller.ops.create_user(username, "Test Authority", "authority", password)
        assert client.post("/api/v1/auth/login", json={"username": username, "password": password, "role": "authority"}).status_code == 200
        state = client.post("/api/v1/runs").json()
        rid = state["run_id"]
        client.post(f"/api/v1/runs/{rid}/commands", json={"command": "pause"})
        assert client.get("/api/v1/health").json()["contract_version"] == "2.0.0"
        assert client.get(f"/api/v1/runs/{rid}/state").status_code == 200
        assert client.get("/api/v1/runs/bad/state").status_code == 404
        with client.websocket_connect(f"/api/v1/runs/{rid}/ws?contract_version=2.0.0") as one, client.websocket_connect(f"/api/v1/runs/{rid}/ws?contract_version=2.0.0") as two:
            assert one.receive_json()["type"] == "snapshot"
            assert two.receive_json()["type"] == "snapshot"
            response = client.post(f"/api/v1/runs/{rid}/commands", json={"command": "step"})
            assert response.status_code == 200
            a, b = one.receive_json(), two.receive_json()
            assert a["state_version"] == b["state_version"] == response.json()["state_version"]
            assert a["state"]["sequence"] == b["state"]["sequence"]


def test_source_switch_does_not_present_replay_as_live(tmp_path):
    c = controller(tmp_path)
    async def run():
        live = await c.command(Command(command="set_source", source_mode="live"))
        assert live.source_mode == "live"
        if c.live_status.status == "available":
            assert live.recent_observations and all(o.source_mode == "live" and o.raw_value == o.value for o in live.recent_observations)
            assert c.live_status.source_timestamp and c.live_status.fetched_at
        else:
            assert not live.latest_assessments and not live.recent_observations
            assert all(station["status"] == "unknown" for station in live.stations)
        replay = await c.command(Command(command="set_source", source_mode="replay"))
        assert replay.generation == live.generation + 1
        assert len(replay.latest_assessments) == 15
    asyncio.run(run())


def test_play_pause_speed_and_immediate_live_fetch(tmp_path):
    c = controller(tmp_path)
    async def run():
        await c.command(Command(command="set_speed", speed=60))
        assert c.speed == 60
        start = c.sequence
        await c.command(Command(command="play"))
        for _ in range(50):
            if c.sequence > start:
                break
            await asyncio.sleep(0.02)
        assert c.sequence > start
        await c.command(Command(command="pause"))
        await asyncio.wait_for(c.clock, timeout=2)
        assert c.status == "paused"
        await c.command(Command(command="set_source", source_mode="live"))
        fetched = asyncio.Event()
        class UnavailableLive:
            async def fetch_latest(self, *_):
                fetched.set()
                return [], SourceStatus(source_mode="live", source_name="test_unavailable", provenance_type="current_gridded_location", status="unavailable", detail="Provider unavailable: test")
        c.live = UnavailableLive()
        await c.command(Command(command="play"))
        await asyncio.wait_for(fetched.wait(), timeout=2)
        assert c.status == "degraded"
    asyncio.run(run())


def test_replay_clock_starts_at_one_x_and_pause_resumes_without_skips(tmp_path):
    c = controller(tmp_path)
    assert c.status == "running" and c.speed == 1
    async def run():
        start = c.sequence
        c.clock = asyncio.create_task(c.run_clock())
        await asyncio.sleep(1.3)
        assert c.sequence >= start + 1
        await c.command(Command(command="pause"))
        paused = c.sequence
        await asyncio.sleep(1.05)
        assert c.sequence == paused
        await c.command(Command(command="set_speed", speed=60))
        await c.command(Command(command="play"))
        await asyncio.sleep(0.2)
        await c.command(Command(command="pause"))
        assert c.sequence > paused
        assert sorted({item.sequence for item in c.chart}) == list(range(min(item.sequence for item in c.chart), c.sequence + 1))
        await c.clock
    asyncio.run(run())


def test_fault_shapes_and_source_recovery():
    source = PreparedSource()
    station, variable = "CHD-01", "temperature_c"
    key = (station, variable)
    sequence = next(i for i in range(50, 100) if source.read_frame(i)[0].value != source.read_frame(i - 1)[0].value)
    prior = source.read_frame(sequence - 1)[0].value
    injector = ScenarioInjector()
    def delivered(fault, magnitude, duration=4):
        injection = Injection(station_id=station, variable=variable, fault_type=fault, magnitude=magnitude, duration_samples=duration, injection_id="fixed", start_sequence=sequence, end_sequence=sequence + duration)
        return [injector.apply(source.read_frame(i), [injection], None, i, {key: prior})[0] for i in range(sequence, sequence + duration + 1)]
    spike = delivered("spike", 12, 1)
    assert spike[0].value == round(spike[0].raw_value + 12, 3) and spike[1].value == spike[1].raw_value
    freeze = delivered("freeze", 0)
    assert all(item.value == prior for item in freeze[:-1]) and freeze[-1].value == freeze[-1].raw_value
    drift = delivered("drift", -12)
    assert [round(item.value - item.raw_value, 2) for item in drift[:-1]] == [-3, -6, -9, -12]
    bias = delivered("bias", 12)
    assert all(round(item.value - item.raw_value, 2) == 12 for item in bias[:-1])
    noise = delivered("noise", 9)
    deviations = [round(item.value - item.raw_value, 2) for item in noise[:-1]]
    assert len(set(deviations)) > 2 and deviations == [round(item.value - item.raw_value, 2) for item in delivered("noise", 9)[:-1]]
    missing = delivered("missing", 0)
    assert all(item.value is None and item.raw_value is not None for item in missing[:-1]) and missing[-1].value == missing[-1].raw_value


def test_spike_duration_and_simultaneous_fault_recover_exactly():
    source = PreparedSource()
    injector = ScenarioInjector()
    start = 60
    for duration in (1, 4):
        spike = Injection(station_id="CHD-01", variable="temperature_c", fault_type="spike", magnitude=9, duration_samples=duration, injection_id="spike", start_sequence=start, end_sequence=start + duration)
        noise = Injection(station_id="MOH-01", variable="humidity_pct", fault_type="bias", magnitude=12, duration_samples=duration, injection_id="bias", start_sequence=start, end_sequence=start + duration)
        for sequence in range(start, start + duration + 1):
            original = source.read_frame(sequence)
            transformed = injector.apply(original, [spike, noise], None, sequence)
            items = {(item.station_id, item.variable): item for item in transformed}
            target = items[("CHD-01", "temperature_c")]
            other = items[("MOH-01", "humidity_pct")]
            if sequence < start + duration:
                assert target.value == round(target.raw_value + 9, 3)
                assert other.value == round(other.raw_value + 12, 3)
                assert target.is_test_overlay and other.is_test_overlay
            else:
                assert target.value == target.raw_value and not target.is_test_overlay
                assert other.value == other.raw_value and not other.is_test_overlay
            assert all(item.value == item.raw_value for item in original)


def test_regional_weather_is_coherent_distinct_and_preserves_source():
    source = PreparedSource()
    injector = ScenarioInjector(seed=26073)
    event = {"start_sequence": 60, "end_sequence": 72, "duration_samples": 12}
    original = source.read_frame(64)
    first = injector.apply(original, [], event, 64)
    again = injector.apply(original, [], event, 64)
    deltas = {variable: [] for variable in ("temperature_c", "pressure_hpa", "humidity_pct")}
    for transformed, repeat in zip(first, again):
        assert transformed.value == repeat.value
        assert transformed.raw_value == next(item.value for item in original if item.station_id == transformed.station_id and item.variable == transformed.variable)
        deltas[transformed.variable].append(round(transformed.value - transformed.raw_value, 3))
    assert all(all(value < 0 for value in deltas[variable]) for variable in ("temperature_c", "pressure_hpa"))
    assert all(value > 0 for value in deltas["humidity_pct"])
    assert all(len(set(values)) > 1 for values in deltas.values())
    spike = Injection(station_id="CHD-01", variable="temperature_c", fault_type="spike", magnitude=9, duration_samples=1, injection_id="compound", start_sequence=64, end_sequence=65)
    compound = injector.apply(original, [spike], event, 64)
    assert compound[0].value == round(first[0].value + 9, 3)
    assert all(compound[index].value == first[index].value for index in range(1, len(first)))
    recovered = injector.apply(source.read_frame(72), [spike], event, 72)
    assert all(item.value == item.raw_value and not item.is_test_overlay for item in recovered)


def test_live_test_overlay_preserves_provider_and_uses_engine(tmp_path):
    c = controller(tmp_path)
    class FixtureProvider:
        async def fetch_latest(self, run_id, generation, sequence):
            frame = c.source.read_frame(570, run_id, generation)
            stamp = "2026-09-19T00:00:00Z"
            copied = [item.model_copy(update={"sample_id": f"{run_id}:{generation}:{sequence}:{item.station_id}:{item.variable}", "sequence": sequence, "timestamp": stamp, "source_timestamp": stamp, "source_mode": "live", "source_name": "fixture_provider"}) for item in frame]
            status = SourceStatus(source_mode="live", source_name="fixture_provider", provenance_type="test_fixture", status="available", source_timestamp=stamp, fetched_at=stamp)
            return copied, status
    c.live = FixtureProvider()
    async def run():
        first = await c.command(Command(command="set_source", source_mode="live"))
        assert first.source_mode == "live" and first.source_timestamp == "2026-09-19T00:00:00Z"
        await c.inject([InjectionSpec(station_id="CHD-01", variable="temperature_c", fault_type="spike", magnitude=15, duration_samples=1)])
        test = await c.step()
        observed = next(o for o in test.recent_observations if o.sequence == test.sequence and o.station_id == "CHD-01" and o.variable == "temperature_c")
        assessed = next(a for a in test.latest_assessments if a.sample_id == observed.sample_id)
        assert observed.is_test_overlay and observed.value == round(observed.raw_value + 15, 3)
        assert assessed.assessment_status == "insufficient_context" and assessed.trust_score is None
        recovered = await c.step()
        clean = next(o for o in recovered.recent_observations if o.sequence == recovered.sequence and o.station_id == "CHD-01" and o.variable == "temperature_c")
        assert clean.value == clean.raw_value and not clean.is_test_overlay
        assert recovered.source_timestamp == first.source_timestamp
    asyncio.run(run())
