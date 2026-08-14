from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


INDEX_COLUMNS = (
    "date",
    "daily_dataset_slug",
    "daily_dataset_url",
    "episode_count",
    "total_bytes",
    "top_avg_score",
    "median_avg_score",
)


class BCSourceError(ValueError):
    """Raised when a replay source or replay body violates the BC source contract."""


@dataclass(frozen=True)
class DailyReplaySource:
    date: str
    dataset_slug: str
    dataset_url: str
    episode_count: int
    total_bytes: int
    top_avg_score: float
    median_avg_score: float


@dataclass(frozen=True)
class ReplayArchiveEntry:
    episode_id: int
    name: str
    bytes: int
    compressed_bytes: int
    crc32: int


@dataclass(frozen=True)
class ReplayQualityRecord:
    episode_id: int
    create_time: str
    avg_score: float
    min_score: float
    sum_score: float
    agent_count: int
    size_bytes: int


@dataclass(frozen=True)
class ReplayEpisodeRecord:
    episode_id: int
    date: str
    path: str
    bytes: int
    sha256: str
    module_version: str
    team_names: tuple[str, str]
    winner_player_index: int
    teacher_player_index: int
    teacher_team_name: str
    teacher_result: str
    teacher_deck_sha256: str
    opponent_deck_sha256: str
    teacher_active_requests: int
    teacher_action_steps: int
    split: str


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise BCSourceError(f"{label} must be an integer") from error
    if parsed <= 0:
        raise BCSourceError(f"{label} must be positive")
    return parsed


def _finite_float(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise BCSourceError(f"{label} must be numeric") from error
    if not (-1e9 < parsed < 1e9):
        raise BCSourceError(f"{label} is outside a sane finite range")
    return parsed


def load_daily_index(path: Path) -> tuple[DailyReplaySource, ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != INDEX_COLUMNS:
            raise BCSourceError(f"unexpected episode-index columns: {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise BCSourceError("episode index is empty")
    sources: list[DailyReplaySource] = []
    seen_dates: set[str] = set()
    for position, row in enumerate(rows):
        date = row["date"]
        if not date or date in seen_dates:
            raise BCSourceError(f"invalid or duplicate date at row {position}")
        seen_dates.add(date)
        slug = row["daily_dataset_slug"]
        url = row["daily_dataset_url"]
        expected_prefix = "pokemon-tcg-ai-battle-episodes-"
        if slug != f"{expected_prefix}{date}":
            raise BCSourceError(f"dataset slug/date mismatch at row {position}")
        if not url.endswith(slug):
            raise BCSourceError(f"dataset URL/slug mismatch at row {position}")
        sources.append(
            DailyReplaySource(
                date=date,
                dataset_slug=slug,
                dataset_url=url,
                episode_count=_positive_int(row["episode_count"], "episode_count"),
                total_bytes=_positive_int(row["total_bytes"], "total_bytes"),
                top_avg_score=_finite_float(row["top_avg_score"], "top_avg_score"),
                median_avg_score=_finite_float(row["median_avg_score"], "median_avg_score"),
            )
        )
    if [source.date for source in sources] != sorted(source.date for source in sources):
        raise BCSourceError("episode index must be sorted by date")
    return tuple(sources)


def archive_inventory(path: Path) -> tuple[ReplayArchiveEntry, ...]:
    if not path.is_file():
        raise BCSourceError(f"replay archive does not exist: {path}")
    entries: list[ReplayArchiveEntry] = []
    metadata_members: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if name != info.filename:
                raise BCSourceError(f"unexpected archive member path: {info.filename}")
            if name == "manifest.csv":
                if name in metadata_members:
                    raise BCSourceError("daily archive contains duplicate manifest.csv")
                metadata_members.add(name)
                continue
            if not name.endswith(".json"):
                raise BCSourceError(f"unexpected archive member path: {info.filename}")
            stem = name.removesuffix(".json")
            if not stem.isdigit() or int(stem) <= 0:
                raise BCSourceError(f"unexpected replay filename: {name}")
            entries.append(
                ReplayArchiveEntry(
                    episode_id=int(stem),
                    name=name,
                    bytes=int(info.file_size),
                    compressed_bytes=int(info.compress_size),
                    crc32=int(info.CRC),
                )
            )
    entries.sort(key=lambda item: item.episode_id)
    if not entries or len({item.episode_id for item in entries}) != len(entries):
        raise BCSourceError("archive episode inventory is empty or contains duplicates")
    return tuple(entries)


def load_archive_manifest(path: Path) -> tuple[ReplayQualityRecord, ...]:
    if not path.is_file():
        raise BCSourceError(f"replay archive does not exist: {path}")
    with zipfile.ZipFile(path) as archive:
        try:
            raw = archive.read("manifest.csv")
        except KeyError as error:
            raise BCSourceError("daily replay archive is missing manifest.csv") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BCSourceError("daily archive manifest is not UTF-8") from error
    reader = csv.DictReader(text.splitlines())
    expected = (
        "episode_id",
        "create_time",
        "avg_score",
        "min_score",
        "sum_score",
        "agent_count",
        "size_bytes",
    )
    if tuple(reader.fieldnames or ()) != expected:
        raise BCSourceError(f"unexpected daily archive manifest columns: {reader.fieldnames}")
    result: list[ReplayQualityRecord] = []
    seen: set[int] = set()
    for position, row in enumerate(reader):
        episode_id = _positive_int(row["episode_id"], "episode_id")
        if episode_id in seen:
            raise BCSourceError(f"duplicate episode ID in daily manifest: {episode_id}")
        seen.add(episode_id)
        create_time = row["create_time"]
        if not create_time:
            raise BCSourceError(f"missing create_time at daily manifest row {position}")
        agent_count = _positive_int(row["agent_count"], "agent_count")
        if agent_count != 2:
            raise BCSourceError(f"episode {episode_id} does not have exactly two agents")
        result.append(
            ReplayQualityRecord(
                episode_id=episode_id,
                create_time=create_time,
                avg_score=_finite_float(row["avg_score"], "avg_score"),
                min_score=_finite_float(row["min_score"], "min_score"),
                sum_score=_finite_float(row["sum_score"], "sum_score"),
                agent_count=agent_count,
                size_bytes=_positive_int(row["size_bytes"], "size_bytes"),
            )
        )
    if not result:
        raise BCSourceError("daily archive manifest is empty")
    return tuple(result)


def quality_select_archive_entries(
    entries: Sequence[ReplayArchiveEntry],
    quality: Sequence[ReplayQualityRecord],
    *,
    count: int,
    minimum_min_score: float | None = None,
) -> tuple[ReplayArchiveEntry, ...]:
    if count <= 0:
        raise BCSourceError("selection count must be positive")
    by_id = {item.episode_id: item for item in entries}
    quality_by_id = {item.episode_id: item for item in quality}
    if set(by_id) != set(quality_by_id):
        raise BCSourceError("archive inventory and daily manifest episode sets differ")
    for episode_id, entry in by_id.items():
        if quality_by_id[episode_id].size_bytes != entry.bytes:
            raise BCSourceError(f"daily manifest size differs for episode {episode_id}")
    candidates = list(quality)
    if minimum_min_score is not None:
        candidates = [item for item in candidates if item.min_score >= minimum_min_score]
    if len(candidates) < count:
        raise BCSourceError(
            f"quality selection needs {count} episodes but only {len(candidates)} satisfy the filter"
        )
    candidates.sort(
        key=lambda item: (-item.min_score, -item.avg_score, -item.sum_score, item.episode_id)
    )
    selected = candidates[:count]
    return tuple(sorted((by_id[item.episode_id] for item in selected), key=lambda item: item.episode_id))


def select_archive_entries(
    entries: Sequence[ReplayArchiveEntry], *, count: int, seed: int
) -> tuple[ReplayArchiveEntry, ...]:
    if count <= 0:
        raise BCSourceError("selection count must be positive")
    if count > len(entries):
        raise BCSourceError("selection count exceeds archive inventory")

    def key(item: ReplayArchiveEntry) -> tuple[str, int]:
        digest = hashlib.sha256(f"{seed}|{item.episode_id}".encode("ascii")).hexdigest()
        return digest, item.episode_id

    return tuple(sorted(sorted(entries, key=key)[:count], key=lambda item: item.episode_id))


def _deck_sha256(deck: Sequence[Any]) -> str:
    if len(deck) != 60 or any(isinstance(value, bool) or not isinstance(value, int) for value in deck):
        raise BCSourceError("replay deck action must contain exactly 60 integer card IDs")
    payload = json.dumps(sorted(int(value) for value in deck), separators=(",", ":")).encode("ascii")
    return _sha256_bytes(payload)


def _split_for_episode(episode_id: int, seed: int) -> str:
    value = int.from_bytes(
        hashlib.sha256(f"split|{seed}|{episode_id}".encode("ascii")).digest()[:8], "big"
    ) % 1000
    if value < 850:
        return "train"
    if value < 950:
        return "validation"
    return "test"


def replay_record_from_bytes(
    raw: bytes,
    *,
    expected_episode_id: int,
    date: str,
    relative_path: str,
    split_seed: int,
) -> ReplayEpisodeRecord:
    try:
        replay = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BCSourceError(f"episode {expected_episode_id} is not valid JSON: {error}") from error
    if not isinstance(replay, Mapping):
        raise BCSourceError("replay top level must be an object")
    info = replay.get("info")
    if not isinstance(info, Mapping) or int(info.get("EpisodeId", -1)) != expected_episode_id:
        raise BCSourceError(f"episode {expected_episode_id} info binding differs")
    teams = info.get("TeamNames")
    if not isinstance(teams, list) or len(teams) != 2 or any(not isinstance(v, str) for v in teams):
        raise BCSourceError(f"episode {expected_episode_id} has invalid TeamNames")
    rewards = replay.get("rewards")
    if rewards == [1, -1]:
        winner = 0
    elif rewards == [-1, 1]:
        winner = 1
    else:
        raise BCSourceError(f"episode {expected_episode_id} has unsupported terminal rewards")
    if replay.get("statuses") != ["DONE", "DONE"]:
        raise BCSourceError(f"episode {expected_episode_id} is not terminal")
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 3:
        raise BCSourceError(f"episode {expected_episode_id} has too few steps")
    deck_step = steps[1]
    if not isinstance(deck_step, list) or len(deck_step) != 2:
        raise BCSourceError(f"episode {expected_episode_id} deck step is malformed")
    decks = []
    for seat in (0, 1):
        row = deck_step[seat]
        if not isinstance(row, Mapping):
            raise BCSourceError(f"episode {expected_episode_id} deck row is malformed")
        action = row.get("action")
        if not isinstance(action, list):
            raise BCSourceError(f"episode {expected_episode_id} deck action is malformed")
        decks.append(action)

    active_requests = 0
    action_steps = 0
    for step_index in range(2, len(steps)):
        previous = steps[step_index - 1]
        current = steps[step_index]
        if not isinstance(previous, list) or not isinstance(current, list):
            raise BCSourceError(f"episode {expected_episode_id} step is malformed")
        prev_teacher = previous[winner]
        current_teacher = current[winner]
        if not isinstance(prev_teacher, Mapping) or not isinstance(current_teacher, Mapping):
            raise BCSourceError(f"episode {expected_episode_id} agent row is malformed")
        observation = prev_teacher.get("observation")
        if prev_teacher.get("status") == "ACTIVE" and isinstance(observation, Mapping) and observation.get("select") is not None:
            active_requests += 1
            action = current_teacher.get("action")
            if isinstance(action, list):
                action_steps += 1
    if active_requests <= 0 or action_steps != active_requests:
        raise BCSourceError(
            f"episode {expected_episode_id} has invalid winner request/action alignment: "
            f"requests={active_requests}, actions={action_steps}"
        )
    return ReplayEpisodeRecord(
        episode_id=expected_episode_id,
        date=date,
        path=relative_path,
        bytes=len(raw),
        sha256=_sha256_bytes(raw),
        module_version=str(replay.get("module_version", "")),
        team_names=(teams[0], teams[1]),
        winner_player_index=winner,
        teacher_player_index=winner,
        teacher_team_name=teams[winner],
        teacher_result="win",
        teacher_deck_sha256=_deck_sha256(decks[winner]),
        opponent_deck_sha256=_deck_sha256(decks[1 - winner]),
        teacher_active_requests=active_requests,
        teacher_action_steps=action_steps,
        split=_split_for_episode(expected_episode_id, split_seed),
    )


def extract_selected_episodes(
    archive_path: Path,
    destination: Path,
    entries: Sequence[ReplayArchiveEntry],
    *,
    date: str,
    split_seed: int,
) -> tuple[ReplayEpisodeRecord, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    selected = {entry.name: entry for entry in entries}
    if len(selected) != len(entries):
        raise BCSourceError("selected archive entries contain duplicates")
    records: list[ReplayEpisodeRecord] = []
    with zipfile.ZipFile(archive_path) as archive:
        for name in sorted(selected, key=lambda value: int(Path(value).stem)):
            entry = selected[name]
            try:
                info = archive.getinfo(name)
            except KeyError as error:
                raise BCSourceError(f"selected replay is absent from archive: {name}") from error
            if info.file_size != entry.bytes or info.CRC != entry.crc32:
                raise BCSourceError(f"selected replay metadata changed: {name}")
            target = destination / name
            partial = target.with_suffix(".json.partial")
            with archive.open(info, "r") as source, partial.open("wb") as sink:
                shutil.copyfileobj(source, sink, length=8 * 1024 * 1024)
            if partial.stat().st_size != entry.bytes:
                partial.unlink(missing_ok=True)
                raise BCSourceError(f"extracted replay byte count differs: {name}")
            partial.replace(target)
            raw = target.read_bytes()
            records.append(
                replay_record_from_bytes(
                    raw,
                    expected_episode_id=entry.episode_id,
                    date=date,
                    relative_path=name,
                    split_seed=split_seed,
                )
            )
    return tuple(records)


def build_source_catalog(
    index_path: Path,
    *,
    local_archives: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    sources = load_daily_index(index_path)
    archives = local_archives or {}
    days = []
    for source in sources:
        row = asdict(source)
        archive = archives.get(source.date)
        if archive is None:
            row["local_archive"] = None
        else:
            inventory = archive_inventory(archive)
            if len(inventory) != source.episode_count:
                raise BCSourceError(
                    f"local archive episode count differs for {source.date}: "
                    f"index={source.episode_count}, archive={len(inventory)}"
                )
            if sum(item.bytes for item in inventory) != source.total_bytes:
                raise BCSourceError(f"local archive uncompressed bytes differ for {source.date}")
            row["local_archive"] = {
                "path": archive.as_posix(),
                "sha256": sha256_file(archive),
                "compressed_bytes": archive.stat().st_size,
                "episodes": len(inventory),
                "uncompressed_bytes": sum(item.bytes for item in inventory),
            }
        days.append(row)
    return {
        "schema_version": 1,
        "source": "kaggle/pokemon-tcg-ai-battle-episodes-index",
        "index_path": index_path.as_posix(),
        "index_sha256": sha256_file(index_path),
        "days": len(days),
        "episodes": sum(source.episode_count for source in sources),
        "uncompressed_bytes": sum(source.total_bytes for source in sources),
        "first_date": sources[0].date,
        "last_date": sources[-1].date,
        "daily_sources": days,
    }


def write_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def episode_records_payload(records: Iterable[ReplayEpisodeRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]
