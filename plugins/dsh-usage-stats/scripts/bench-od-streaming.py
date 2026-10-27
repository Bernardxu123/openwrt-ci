# Compare the two routes the way DSH actually drives them: STREAMING.
#
# Earlier tests used non-streaming calls, which hid the real difference. In
# streaming mode the protocols are structurally different:
#
#   amr /v1/responses        -> typed SSE events. For ~114 tokens of work the
#                               server sent 128 events: 59 output_text.delta,
#                               55 reasoning_summary_text.delta, plus lifecycle
#                               events (created / in_progress / item.added /
#                               item.done / content_part.added / ... / completed).
#                               Usage rides on `response.completed`, not on deltas.
#
#   magpie /v1/chat/completions -> one `chat.completion.chunk` per token.
#
# More events means more framing, more parser work and a higher per-event latency
# floor for the same number of tokens. This script measures tokens-per-second
# using the usage that each protocol actually reports, and also records the
# event count so the framing overhead is visible next to the throughput.
import json
import os
import re
import statistics
import subprocess
import sys

CRED = os.path.expanduser("~/.dsh/.credentials.yaml")


def ref(name: str) -> str:
    with open(CRED, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(rf"^\s+{re.escape(name)}:\s*(\S+)\s*$", line)
            if m:
                return m.group(1)
    raise SystemExit(f"{name} missing")


OD_KEY = ref("OD_API_KEY")
MAGPIE_KEY = "magpie"
try:
    with open(os.path.expanduser("~/.dsh/.env"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^MAGPIE_GATEWAY_KEY\s*=\s*(\S+)\s*$", line)
            if m:
                MAGPIE_KEY = m.group(1)
except FileNotFoundError:
    pass

ARMS = {
    "od": ("https://amr-link.open-design.ai/v1/responses", OD_KEY, "deepseek-v4.1-flash", "responses"),
    "magpie": ("http://127.0.0.1:3425/v1/chat/completions", MAGPIE_KEY, "opendesign/deepseek-v4.1-flash", "chat"),
}

PROMPT = "Write the numbers 1 to 400 separated by commas. No other text, no explanation."
BUDGET = 900
ROUNDS = 8

CHILD = r"""
import json, sys, time, urllib.request

url, key, model, protocol, prompt, budget = sys.argv[1:7]
if protocol == "responses":
    payload = {"model": model, "input": prompt,
               "max_output_tokens": int(budget), "stream": True}
else:
    payload = {"model": model, "max_tokens": int(budget), "temperature": 0,
               "stream": True, "stream_options": {"include_usage": True},
               "messages": [{"role": "user", "content": prompt}]}

req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
req.add_header("authorization", f"Bearer {key}")
req.add_header("content-type", "application/json")

t0 = time.perf_counter()
tok = 0
events = 0
first = last = None

with urllib.request.urlopen(req, timeout=300) as resp:
    for raw in resp:
        now = time.perf_counter() - t0
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data: "):
            continue
        body = line[6:].strip()
        if not body or body == "[DONE]":
            continue
        try:
            obj = json.loads(body)
        except json.JSONDecodeError:
            continue
        events += 1

        # Usage: responses puts it on the terminal `response.completed` event
        # (inside `response.usage`), chat puts it on a trailing chunk.
        usage = obj.get("usage")
        if not usage:
            usage = (obj.get("response") or {}).get("usage") or {}
        if usage:
            val = usage.get("output_tokens") or usage.get("completion_tokens")
            if val:
                tok = val

        if protocol == "responses":
            etype = obj.get("type") or ""
            if etype.endswith(".delta"):
                if first is None:
                    first = now
                last = now
        else:
            for ch in obj.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content") or d.get("reasoning"):
                    if first is None:
                        first = now
                    last = now

wall = time.perf_counter() - t0
print(json.dumps({
    "wall": wall, "tok": tok, "events": events,
    "gen": (last - first) if (first and last) else 0,
    "ttft": first,
}))
"""


def run(arm: str) -> dict:
    url, key, model, proto = ARMS[arm]
    out = subprocess.run(
        [sys.executable, "-c", CHILD, url, key, model, proto, PROMPT, str(BUDGET)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=360,
    )
    if out.returncode != 0:
        return {"error": (out.stderr or out.stdout).strip()[:200]}
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": "unparseable"}


per_arm: dict[str, list[dict]] = {arm: [] for arm in ARMS}
paired = []
for rnd in range(ROUNDS):
    row = {}
    for arm in ARMS:
        r = run(arm)
        if "error" in r or not r.get("tok"):
            print(f"  round{rnd+1} {arm:<7} ERROR {r.get('error') or 'no usage'}")
            continue
        r["rate"] = r["tok"] / r["wall"]
        per_arm[arm].append(r)
        row[arm] = r
    if len(row) == 2:
        d = row["magpie"]["rate"] - row["od"]["rate"]
        paired.append(d)
        print(f"  round{rnd+1:2d}  od {row['od']['rate']:6.1f} tok/s "
              f"(ev={row['od']['events']:3d}, gen={row['od']['gen']:4.2f}s)   "
              f"magpie {row['magpie']['rate']:6.1f} tok/s "
              f"(ev={row['magpie']['events']:3d}, gen={row['magpie']['gen']:4.2f}s)   "
              f"diff {d:+6.1f}")

print(f"\n{'='*78}\nSTREAMING COMPARISON  ({BUDGET} tokens, {ROUNDS} rounds)")
print(f"  {'arm':<8} {'tok/s med':>10} {'events med':>11} {'gen s med':>10} {'ttft med':>9}")
for arm, rows in per_arm.items():
    if not rows:
        continue
    print(f"  {arm:<8} {statistics.median(r['rate'] for r in rows):10.1f} "
          f"{statistics.median(r['events'] for r in rows):11.0f} "
          f"{statistics.median(r['gen'] for r in rows):10.2f} "
          f"{statistics.median(r['ttft'] for r in rows):8.2f}s")

if paired:
    mean_d = statistics.mean(paired)
    wins = sum(1 for d in paired if d > 0)
    print(f"\n  paired diff (magpie - od): mean {mean_d:+.1f} tok/s, "
          f"median {statistics.median(paired):+.1f}, magpie faster {wins}/{len(paired)}")
    base = statistics.median(r["rate"] for r in per_arm["od"])
    print(f"  ratio vs od median ({base:.1f}): {statistics.median(paired)/base*100:+.1f}%")

    # Generation-only rate: token count over the window where deltas actually
    # arrived. This strips connect + prefill and isolates decode speed.
    print(f"\n  generation-only rate (tokens / delta window):")
    for arm, rows in per_arm.items():
        if not rows:
            continue
        g = [r["tok"] / r["gen"] for r in rows if r["gen"] > 0]
        if g:
            print(f"    {arm:<8} {statistics.median(g):6.1f} tok/s")
