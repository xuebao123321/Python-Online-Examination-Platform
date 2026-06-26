"""
Turso HTTP API 适配器
通过 HTTP 请求访问 Turso 云数据库，无需原生依赖。
模拟 sqlite3 的 row_factory 和基本接口。
"""

import json
import urllib.request
import urllib.error


class TursoRow:
    """模拟 sqlite3.Row，支持按列名和索引访问"""
    def __init__(self, columns, values):
        self._columns = columns
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._columns.index(key)]

    def keys(self):
        return self._columns

    def __iter__(self):
        return iter(self._values)

    def __repr__(self):
        return dict(zip(self._columns, self._values)).__repr__()


class TursoConnection:
    """模拟 sqlite3.Connection 基本接口"""
    def __init__(self, url, token):
        self._base_url = url.replace("libsql://", "https://")
        self._token = token
        self.row_factory = None
        self.total_changes = 0

    def _to_turso_arg(self, val):
        """将 Python 值转为 Turso 类型格式"""
        if val is None:
            return {"type": "null"}
        if isinstance(val, bool):
            return {"type": "integer", "value": "1" if val else "0"}
        if isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        if isinstance(val, float):
            return {"type": "real", "value": str(val)}
        return {"type": "text", "value": str(val)}

    def _request(self, sql, params=None):
        """发送 HTTP 请求到 Turso"""
        args = [self._to_turso_arg(p) for p in params] if params else []
        body = {
            "requests": [{
                "type": "execute",
                "stmt": {"sql": sql, "args": args}
            }]
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v2/pipeline",
            data=data,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            raise Exception(f"Turso HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise Exception(f"Turso 连接失败: {e.reason}") from e

    def execute(self, sql, params=None):
        """执行 SQL，返回 Cursor 模拟对象"""
        result = self._request(sql, params)
        cursor = TursoCursor(self)
        if "results" in result and result["results"]:
            r = result["results"][0]
            # 外层 type 是 "ok"，内层 response.type 是 "execute"
            if "response" in r:
                resp = r["response"]
                if "result" in resp:
                    res = resp["result"]
                    cursor._columns = [c["name"] for c in res.get("cols", [])]
                    cursor._rows = []
                    for row_data in res.get("rows", []):
                        values = [v.get("value", None) for v in row_data]
                        cursor._rows.append((cursor._columns, values))
                    cursor._affected_rows = res.get("affected_row_count", 0)
                    cursor.lastrowid = res.get("last_insert_rowid")
                    self.total_changes += cursor._affected_rows
        return cursor

    def executemany(self, sql, params_list):
        """批量执行"""
        requests = []
        for params in params_list:
            requests.append({
                "type": "execute",
                "stmt": {"sql": sql, "args": list(params) if params else []}
            })
        body = json.dumps({"requests": requests}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v2/pipeline",
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            json.loads(resp.read().decode("utf-8"))
        self.total_changes += len(params_list)

    def cursor(self):
        """返回一个新 cursor"""
        return TursoCursor(self)

    def commit(self):
        pass  # Turso 自动提交

    def close(self):
        pass


class TursoCursor:
    """模拟 sqlite3.Cursor"""
    def __init__(self, connection):
        self.connection = connection
        self._columns = []
        self._rows = []
        self._idx = 0
        self._affected_rows = 0
        self.lastrowid = None

    def execute(self, sql, params=None):
        """执行 SQL（委托给 connection）"""
        result = self.connection.execute(sql, params)
        self._columns = result._columns
        self._rows = result._rows
        self._affected_rows = result._affected_rows
        self.lastrowid = result.lastrowid
        return self

    def executemany(self, sql, params_list):
        self.connection.executemany(sql, params_list)

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return TursoRow(row[0], row[1])

    def fetchall(self):
        return [TursoRow(r[0], r[1]) for r in self._rows[self._idx:]]

    @property
    def rowcount(self):
        return self._affected_rows
