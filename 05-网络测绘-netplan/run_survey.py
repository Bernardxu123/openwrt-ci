#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
survey.sh 的 Windows 等价物 —— 一键：采集 -> 定位 -> 导出 geo.json

  python run_survey.py               # 采一轮，定位，导出 geo.json
  python run_survey.py --watch 60    # 每 60 秒一轮，持续采集（Ctrl+C 停）
  python run_survey.py --tag 客厅     # 给这批数据打标签

采集完成后，把生成的 geo.json 拖进网页左侧「导入 geo.json」即可。
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script)] + list(args)
    print("\n$ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, default=0)
    ap.add_argument("--probe", type=int, default=3)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default="geo.json")
    args = ap.parse_args()

    if args.watch <= 0:
        rc = run("survey.py", "--probe", str(args.probe), "--tag", args.tag)
        if rc != 0:
            print("采集失败", file=sys.stderr)
            return rc
        run("locate.py", "--export", args.out)
        print("\n完成：%s\n把 geo.json 拖进网页左侧「导入 geo.json」。" % args.out)
        return 0

    # 持续采集：每轮采完就重新定位导出
    print("持续采集模式，每 %d 秒一轮。Ctrl+C 停止。" % args.watch)
    n = 0
    try:
        while True:
            n += 1
            print("\n" + "=" * 70)
            print("第 %d 轮" % n)
            run("survey.py", "--probe", str(args.probe), "--tag", args.tag)
            run("locate.py", "--export", args.out)
            time.sleep(args.watch)
    except KeyboardInterrupt:
        print("\n已停止。最后一版结果在 %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
