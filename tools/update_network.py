#!/usr/bin/env python3
"""Rhein-Main Live: rebuild the embedded S/U/Tram network from Transitous and compare it
with the baseline.

Usage:
  python3 update_network.py --baseline network.json --baseline-topo topology.json \
      [--html rhein-main-live.html] [--out new_network.json]
  (also writes new_network.topology.json next to --out)

Harvests scheduled S-Bahn/U-Bahn/Tram segments for the next weekday (12:00-13:10 and
07:30-08:10 local) across the Rhein-Main area, builds the network JSON (lines, edges,
stations), prints a diff against the baseline, and, if --html is given and there are
changes, injects the new network into the HTML (window.NET=...).
Exit code 0 = no change, 10 = changed, 2 = harvest failed.
"""
import argparse, datetime, json, math, os, re, ssl, sys, time, urllib.request
from zoneinfo import ZoneInfo

API = "https://api.transitous.org/api/v1/map/trips"
MODES = {"METRO": "S", "SUBURBAN": "S", "SUBWAY": "U", "TRAM": "T"}
BBOX = (49.80, 50.45, 8.05, 9.25)  # lat0, lat1, lon0, lon1
UA = {"User-Agent": "rhein-main-live-network-check/1.0"}


def ssl_ctx():
    ca = "/root/.ccr/ca-bundle.crt"
    return ssl.create_default_context(cafile=ca) if os.path.exists(ca) else ssl.create_default_context()


def next_weekday(tz):
    d = datetime.datetime.now(tz).date() + datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


def harvest():
    tz = ZoneInfo("Europe/Berlin")
    day = next_weekday(tz)
    starts = [datetime.datetime.combine(day, datetime.time(12, 0), tz) + datetime.timedelta(minutes=10 * k) for k in range(7)]
    starts += [datetime.datetime.combine(day, datetime.time(7, 30), tz) + datetime.timedelta(minutes=10 * k) for k in range(4)]
    lat0, lat1, lon0, lon1 = BBOX
    n = 3
    tiles = [(lat0 + (lat1 - lat0) * i / n, lon0 + (lon1 - lon0) * j / n,
              lat0 + (lat1 - lat0) * (i + 1) / n, lon0 + (lon1 - lon0) * (j + 1) / n)
             for i in range(n) for j in range(n)]
    ctx, segs, fails = ssl_ctx(), [], 0
    fmt = lambda t: t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for a, b, c, d in tiles:
        for w in starts:
            q = (f"{API}?min={a:.4f},{b:.4f}&max={c:.4f},{d:.4f}"
                 f"&startTime={fmt(w)}&endTime={fmt(w + datetime.timedelta(minutes=10))}&zoom=14")
            r = None
            for _ in range(3):
                try:
                    r = json.load(urllib.request.urlopen(urllib.request.Request(q, headers=UA), context=ctx, timeout=60))
                    break
                except Exception:
                    time.sleep(3)
            if not isinstance(r, list):
                fails += 1
                continue
            segs += [x for x in r if x.get("mode") in MODES]
    return segs, fails, day


def dec(s):
    i = lat = lng = 0; out = []
    while i < len(s):
        for k in range(2):
            r = sh = 0
            while True:
                b = ord(s[i]) - 63; i += 1; r |= (b & 31) << sh; sh += 5
                if b < 32: break
            v = ~(r >> 1) if r & 1 else r >> 1
            if k == 0: lat += v
            else: lng += v
        out.append((lat / 1e5, lng / 1e5))
    return out


def enc(pts):
    out = []; pl = pg = 0
    for la, lo in pts:
        a = round(la * 1e5); b = round(lo * 1e5)
        for v in (a - pl, b - pg):
            v = ~(v << 1) if v < 0 else v << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1f)) + 63)); v >>= 5
            out.append(chr(v + 63))
        pl, pg = a, b
    return "".join(out)


def dp(pts, eps=4e-5):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]; best = 0; idx = 0
    for i in range(1, len(pts) - 1):
        p = pts[i]; dx = b[1] - a[1]; dy = b[0] - a[0]
        d = math.hypot(p[0] - a[0], p[1] - a[1]) if dx == dy == 0 else abs(dy * (p[1] - a[1]) - dx * (p[0] - a[0])) / math.hypot(dx, dy)
        if d > best: best = d; idx = i
    if best > eps: return dp(pts[:idx + 1], eps)[:-1] + dp(pts[idx:], eps)
    return [a, b]


def build(segs):
    lines, edges, st, topo = {}, {}, {}, set()

    def node(p):
        k = p.get("parentId") or p["stopId"]
        s = st.setdefault(k, {"n": p["name"], "pts": [], "m": set(), "l": set()})
        s["pts"].append((p["lat"], p["lon"])); return k, s

    for x in segs:
        l = x["trips"][0].get("routeShortName"); m = MODES[x["mode"]]
        if not l: continue
        lines.setdefault(l, {"c": "#" + (x.get("routeColor") or "888888"), "m": m})
        fk, fs = node(x["from"]); tk, ts = node(x["to"])
        for s in (fs, ts): s["m"].add(m); s["l"].add(l)
        if fk == tk: continue
        nm = lambda n: re.sub(r"^Frankfurt \(Main\)\s*", "", n)
        topo.add("|".join([l] + sorted([nm(x["from"]["name"]), nm(x["to"]["name"])])))
        key = tuple(sorted((fk, tk)))
        e = edges.setdefault(key, {"geom": None, "lines": set()})
        e["lines"].add(l)
        if e["geom"] is None and x.get("polyline"):
            pts = dec(x["polyline"])
            if fk != key[0]: pts = pts[::-1]
            e["geom"] = pts

    def lkey(l):
        n = re.findall(r"\d+", l)
        return ("SUT".index(lines[l]["m"]), int(n[0]) if n else 999, l)

    out_edges = [[enc(dp(e["geom"])), sorted(e["lines"], key=lkey)] for e in edges.values() if e["geom"]]
    raw = []
    for s in st.values():
        la = sum(p[0] for p in s["pts"]) / len(s["pts"]); lo = sum(p[1] for p in s["pts"]) / len(s["pts"])
        raw.append([re.sub(r"^Frankfurt \(Main\)\s*", "", s["n"]), round(la, 5), round(lo, 5),
                    "".join(sorted(s["m"], key="SUT".index)), len(s["l"])])
    merged = []
    for s in sorted(raw, key=lambda s: (-("S" in s[3] or "U" in s[3]), -s[4])):
        for m in merged:
            if m[0] == s[0] and math.hypot((m[1] - s[1]) * 111, (m[2] - s[2]) * 71) < 0.4:
                m[3] = "".join(sorted(set(m[3] + s[3]), key="SUT".index)); m[4] = max(m[4], s[4]); break
        else:
            merged.append(list(s))
    lines = {k: lines[k] for k in sorted(lines, key=lkey)}
    return {"lines": lines, "edges": out_edges, "stations": merged}, sorted(topo)


def diff(old, new, old_topo, new_topo):
    ol, nl = set(old["lines"]), set(new["lines"])
    ot, nt = set(old_topo), set(new_topo)
    added, removed = sorted(nt - ot), sorted(ot - nt)
    st = lambda t: {n for e in t for n in e.split("|")[1:]}
    return {
        "lines_added": sorted(nl - ol), "lines_removed": sorted(ol - nl),
        "stations_added": sorted(st(nt) - st(ot)), "stations_removed": sorted(st(ot) - st(nt)),
        "connections_added": added, "connections_removed": removed,
        "colors_changed": {l: [old["lines"][l]["c"], new["lines"][l]["c"]] for l in nl & ol if old["lines"][l]["c"] != new["lines"][l]["c"]},
        "counts": {"alt": [len(ol), len(st(ot)), len(ot)], "neu": [len(nl), len(st(nt)), len(nt)]},
    }


def significant(d):
    # Single sporadic trip variants cause a little noise; flag real changes.
    return bool(d["lines_added"] or d["lines_removed"] or d["colors_changed"]
                or len(d["stations_added"]) + len(d["stations_removed"]) >= 2
                or len(d["connections_added"]) + len(d["connections_removed"]) >= 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="network.json currently embedded in the page")
    ap.add_argument("--baseline-topo", required=True, help="topology.json from the last build")
    ap.add_argument("--html")
    ap.add_argument("--out", default="new_network.json")
    a = ap.parse_args()
    segs, fails, day = harvest()
    print(f"Stichtag {day}, {len(segs)} Segmente, {fails} fehlgeschlagene Abfragen")
    if len(segs) < 5000 or fails > 20:
        print("ABBRUCH: zu wenige Daten, Datenquelle vermutlich gestört."); sys.exit(2)
    new, topo = build(segs)
    json.dump(topo, open(os.path.splitext(a.out)[0] + ".topology.json", "w"), ensure_ascii=False, indent=0)
    s = json.dumps(new, ensure_ascii=False, separators=(",", ":"))
    open(a.out, "w").write(s)
    old = json.load(open(a.baseline))
    d = diff(old, new, json.load(open(a.baseline_topo)), topo)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    if not significant(d):
        print("ERGEBNIS: keine relevanten Änderungen."); sys.exit(0)
    if a.html:
        h = open(a.html).read()
        h2, n = re.subn(r"<script>window\.NET=.*?;</script>", lambda m: "<script>window.NET=" + s + ";</script>", h, count=1, flags=re.S)
        if n != 1: print("WARNUNG: window.NET nicht im HTML gefunden."); sys.exit(10)
        open(a.html, "w").write(h2)
        print(f"HTML aktualisiert: {a.html}")
    print("ERGEBNIS: Netz hat sich geändert."); sys.exit(10)


if __name__ == "__main__":
    main()
