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
            """
        )
        self._db.commit()

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
    def finish(self, umo: str, game: dict, result: str, score: int) -> None:
        """归档案件并结算个人积分。result: solved / failed / abandoned / expired"""
        m = game["meta"]
        with self._lock:
            self._db.execute(
                "INSERT INTO cases(umo,title,theme,trick,style,result,score,data,ended) VALUES(?,?,?,?,?,?,?,?,?)",
                (umo, game["case"]["title"], m["theme"], m["trick"], m["style"], result, score,
                 json.dumps(game["case"], ensure_ascii=False), time.time()),
            )
            if result in ("solved", "failed"):
                for uid, p in game["players"].items():
                    self._db.execute(
                        "INSERT INTO scores(umo,uid,name,pts,solved,games) VALUES(?,?,?,?,?,1) "
                        "ON CONFLICT(umo,uid) DO UPDATE SET name=excluded.name, pts=pts+excluded.pts, solved=solved+excluded.solved, games=games+1",
                        (umo, uid, p["name"], p["pts"], 1 if result == "solved" else 0),
                    )
            self._db.execute("DELETE FROM games WHERE umo=?", (umo,))
            self._db.commit()

    def recent_combos(self, umo: str, n: int = 6) -> tuple[str, ...]:
        with self._lock:
            rows = self._db.execute("SELECT theme, trick FROM cases WHERE umo=? ORDER BY id DESC LIMIT ?", (umo, n)).fetchall()
        return tuple(f"{a}:{b}" for a, b in rows)

    def ranking(self, umo: str, n: int = 10) -> list[tuple[str, int, int, int]]:
        with self._lock:
            return self._db.execute(
                "SELECT name, pts, solved, games FROM scores WHERE umo=? ORDER BY pts DESC, solved DESC LIMIT ?", (umo, n)
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
