"""SQLite 存储：进行中的对局、个人积分、已结案件。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path


class Storage:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                umo TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scores (
                umo TEXT NOT NULL,
                uid TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                pts INTEGER NOT NULL DEFAULT 0,
                solved INTEGER NOT NULL DEFAULT 0,
                games INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (umo, uid)
            );
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                umo TEXT NOT NULL,
                title TEXT NOT NULL,
                theme TEXT NOT NULL,
                trick TEXT NOT NULL,
                style TEXT NOT NULL,
                result TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                data TEXT NOT NULL,
                ended REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ratings (
                case_id INTEGER NOT NULL,
                uid TEXT NOT NULL,
                stars INTEGER NOT NULL,
                PRIMARY KEY (case_id, uid)
            );
            CREATE TABLE IF NOT EXISTS starts (
                umo TEXT NOT NULL,
                ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gen_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                umo TEXT NOT NULL,
                ts REAL NOT NULL,
                combo TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                ok INTEGER NOT NULL,
                secs REAL NOT NULL,
                reasons TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS subs (
                umo TEXT PRIMARY KEY,
                weekday INTEGER NOT NULL,
                hm TEXT NOT NULL,
                last TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self._migrate()
        self._db.commit()

    def _migrate(self) -> None:
        def cols(t):
            return {r[1] for r in self._db.execute(f"PRAGMA table_info({t})")}
        sc = cols("scores")
        for c in ("breaks", "wrongs", "quick"):
            if c not in sc:
                self._db.execute(f"ALTER TABLE scores ADD COLUMN {c} INTEGER NOT NULL DEFAULT 0")
        if "replay_of" not in cols("cases"):
            self._db.execute("ALTER TABLE cases ADD COLUMN replay_of INTEGER")

    # ------------------------------------------------------------ 对局
    def load(self, umo: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM games WHERE umo=?", (umo,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, umo: str, game: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO games(umo, data, updated) VALUES(?,?,?) ON CONFLICT(umo) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                (umo, json.dumps(game, ensure_ascii=False), game.get("updated") or time.time()),
            )
            self._db.commit()

    def drop(self, umo: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM games WHERE umo=?", (umo,))
            self._db.commit()

    # ------------------------------------------------------------ 结案
    def finish(self, umo: str, game: dict, result: str, score: int) -> int:
        """归档案件并结算个人积分，返回案件编号。result: solved / failed / abandoned / expired"""
        m = game["meta"]
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO cases(umo,title,theme,trick,style,result,score,data,ended,replay_of) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (umo, game["case"]["title"], m["theme"], m["trick"], m["style"], result, score,
                 json.dumps({"case": game["case"], "meta": m}, ensure_ascii=False), time.time(), m.get("replay_of")),
            )
            case_id = cur.lastrowid
            if result in ("solved", "failed"):
                for uid, p in game["players"].items():
                    self._db.execute(
                        "INSERT INTO scores(umo,uid,name,pts,solved,games,breaks,wrongs,quick) VALUES(?,?,?,?,?,1,?,?,?) "
                        "ON CONFLICT(umo,uid) DO UPDATE SET name=excluded.name, pts=pts+excluded.pts, solved=solved+excluded.solved, games=games+1, "
                        "breaks=breaks+excluded.breaks, wrongs=wrongs+excluded.wrongs, quick=quick+excluded.quick",
                        (umo, uid, p["name"], p["pts"], 1 if result == "solved" else 0, p.get("breaks", 0), p.get("wrongs", 0), p.get("quick", 0)),
                    )
            self._db.execute("DELETE FROM games WHERE umo=?", (umo,))
            self._db.commit()
        return case_id

    # ------------------------------------------------------------ 案件库
    def last_case(self, umo: str) -> tuple[int, str] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, title FROM cases WHERE umo=? AND result IN ('solved','failed','abandoned') ORDER BY id DESC LIMIT 1", (umo,)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def rate(self, case_id: int, uid: str, stars: int) -> tuple[float, int]:
        with self._lock:
            self._db.execute(
                "INSERT INTO ratings(case_id,uid,stars) VALUES(?,?,?) ON CONFLICT(case_id,uid) DO UPDATE SET stars=excluded.stars",
                (case_id, uid, stars),
            )
            self._db.commit()
            row = self._db.execute("SELECT AVG(stars), COUNT(*) FROM ratings WHERE case_id=?", (case_id,)).fetchone()
        return float(row[0] or 0), int(row[1] or 0)

    def library(self, min_avg: float, limit: int = 15) -> list[tuple]:
        """精品案件：原创（非重玩）且平均分达标。返回 (id, title, theme, style, avg, n, plays)。
        评分记在原案或它的重玩上都算原案的。"""
        with self._lock:
            return self._db.execute(
                """
                SELECT c.id, c.title, c.theme, c.style, AVG(r.stars) AS avg, COUNT(r.stars) AS n,
                       1 + (SELECT COUNT(*) FROM cases x WHERE x.replay_of = c.id) AS plays
                FROM cases c JOIN ratings r ON r.case_id = c.id OR r.case_id IN (SELECT id FROM cases y WHERE y.replay_of = c.id)
                WHERE c.replay_of IS NULL AND c.result IN ('solved','failed','abandoned')
                GROUP BY c.id HAVING avg >= ?
                ORDER BY avg DESC, n DESC, c.id DESC LIMIT ?
                """,
                (min_avg, limit),
            ).fetchall()

    def case_data(self, case_id: int) -> dict | None:
        """取归档案件，返回 {"case":..., "meta":...}；兼容早期只存 case 的格式。"""
        with self._lock:
            row = self._db.execute("SELECT data, theme, trick, style, replay_of FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            return None
        d = json.loads(row[0])
        if "case" not in d:
            d = {"case": d, "meta": {"theme": row[1], "trick": row[2], "style": row[3], "diff": "normal"}}
        d["origin"] = row[4] or case_id
        return d

    # ------------------------------------------------------------ 生成日志
    def log_gen(self, umo: str, combo: str, attempts: int, ok: bool, secs: float, reasons: list[str]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO gen_log(umo,ts,combo,attempts,ok,secs,reasons) VALUES(?,?,?,?,?,?,?)",
                (umo, time.time(), combo, attempts, 1 if ok else 0, secs, json.dumps(reasons, ensure_ascii=False)),
            )
            self._db.commit()

    def gen_stats(self, n: int = 30) -> list[tuple]:
        """最近 n 次生成：(ts, combo, attempts, ok, secs, reasons)"""
        with self._lock:
            rows = self._db.execute("SELECT ts, combo, attempts, ok, secs, reasons FROM gen_log ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [(r[0], r[1], r[2], r[3], r[4], json.loads(r[5] or "[]")) for r in rows]

    # ------------------------------------------------------------ 开局次数
    def add_start(self, umo: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO starts(umo, ts) VALUES(?,?)", (umo, time.time()))
            self._db.commit()

    def starts_since(self, umo: str, ts: float) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM starts WHERE umo=? AND ts>=?", (umo, ts)).fetchone()[0]

    # ------------------------------------------------------------ 悬案之夜订阅
    def subscribe(self, umo: str, weekday: int, hm: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO subs(umo,weekday,hm) VALUES(?,?,?) ON CONFLICT(umo) DO UPDATE SET weekday=excluded.weekday, hm=excluded.hm",
                (umo, weekday, hm),
            )
            self._db.commit()

    def unsubscribe(self, umo: str) -> bool:
        with self._lock:
            n = self._db.execute("DELETE FROM subs WHERE umo=?", (umo,)).rowcount
            self._db.commit()
        return n > 0

    def subs(self) -> list[tuple[str, int, str, str]]:
        with self._lock:
            return self._db.execute("SELECT umo, weekday, hm, last FROM subs").fetchall()

    def sub_of(self, umo: str) -> tuple[int, str] | None:
        with self._lock:
            row = self._db.execute("SELECT weekday, hm FROM subs WHERE umo=?", (umo,)).fetchone()
        return (row[0], row[1]) if row else None

    def mark_sub(self, umo: str, day: str) -> None:
        with self._lock:
            self._db.execute("UPDATE subs SET last=? WHERE umo=?", (day, umo))
            self._db.commit()

    # ------------------------------------------------------------ 私下推理
    def games_with_player(self, uid: str) -> list[tuple[str, dict]]:
        with self._lock:
            rows = self._db.execute("SELECT umo, data FROM games").fetchall()
        out = []
        for umo, data in rows:
            g = json.loads(data)
            if uid in g.get("players", {}):
                out.append((umo, g))
        return out

    def player_names(self, umo: str) -> list[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT name FROM scores WHERE umo=?", (umo,)).fetchall()]

    def recent_combos(self, umo: str, n: int = 6) -> tuple[str, ...]:
        with self._lock:
            rows = self._db.execute("SELECT theme, trick FROM cases WHERE umo=? ORDER BY id DESC LIMIT ?", (umo, n)).fetchall()
        return tuple(f"{a}:{b}" for a, b in rows)

    def ranking(self, umo: str, n: int = 10) -> list[tuple[str, int, int, int, int, int, int]]:
        """(name, pts, solved, games, breaks, wrongs, quick)"""
        with self._lock:
            return self._db.execute(
                "SELECT name, pts, solved, games, breaks, wrongs, quick FROM scores WHERE umo=? ORDER BY pts DESC, solved DESC LIMIT ?", (umo, n)
            ).fetchall()

    def stats(self, umo: str) -> tuple[int, int]:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*), SUM(result='solved') FROM cases WHERE umo=? AND result IN ('solved','failed')", (umo,)
            ).fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    def close(self) -> None:
        with self._lock:
            self._db.close()
