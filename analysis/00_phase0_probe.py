"""
Phase 0 — 나라장터 공공 ERP RFP 수집 실현가능성 점검

목적: 본수집(Phase 1)에 들어가기 전에 세 가지를 확인한다.
  (1) 키워드로 몇 건이 매칭되는가
  (2) 매칭 건에 제안요청서가 실제로 붙어 있는가
  (3) 첨부파일이 어떤 포맷인가

확인됨: 목록 API(getBidPblancListInfoServcPPSSrch) 응답 안에
        ntceSpecDocUrl1~10 / ntceSpecFileNm1~10 필드로 첨부파일
        URL·파일명이 이미 포함되어 있음. 별도 첨부파일 API 불필요.

이번 개정:
  - rows=100 → 500으로 상향 (호출 횟수 약 5분의 1)
  - 한 달 처리 끝날 때마다 즉시 matched.json에 저장 (중단돼도 유실 없음)
  - 이미 완료된 달은 건너뛰고 이어서 진행 (재실행 시 처음부터 다시 안 함)
  - 타임아웃 재시도 대기시간을 2초→5초→10초로 점진 증가

준비:
  1. 이 파일과 같은 폴더(또는 프로젝트 루트)에 .env 파일 생성
  2. .env 안에 아래 한 줄 추가:
       G2B_SERVICE_KEY=발급받은_인증키
  3. pip install requests python-dotenv

사용법:
  python 00_phase0_probe.py probe
  python 00_phase0_probe.py collect                     # 기본 8개월(202601~202608), 중단 후 재실행하면 이어서 진행
  python 00_phase0_probe.py collect 202608 202608       # 1개월만 테스트
  python 00_phase0_probe.py collect --restart           # 처음부터 다시 (진행 기록 무시)
  python 00_phase0_probe.py audit
"""

import os
import sys
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[안내] python-dotenv 미설치 — .env 자동 로딩 생략, 환경변수만 사용합니다.")
    print("       설치하려면: pip install python-dotenv\n")

# ---------------------------------------------------------------- 설정

_raw_key = os.environ.get("G2B_SERVICE_KEY", "")
SERVICE_KEY = unquote(_raw_key) if "%" in _raw_key else _raw_key

LIST_ENDPOINT = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"

OUT = Path("phase0_out")
OUT.mkdir(exist_ok=True)

MATCHED_PATH = OUT / "matched.json"
PROGRESS_PATH = OUT / "collect_progress.json"

# ---------------------------------------------------------------- 키워드

TIER_A = ["ERP", "전사적자원관리", "재정정보시스템", "예산회계시스템", "자원관리시스템"]
TIER_B = ["경영정보시스템", "통합정보시스템", "회계시스템", "인사시스템", "자산관리시스템"]
TIER_C_HEAD = ["차세대", "정보시스템"]
TIER_C_TAIL = ["구축", "고도화", "재구축", "개발", "시스템"]


def classify(title: str):
    t = title.replace(" ", "")
    for kw in TIER_A:
        if kw.replace(" ", "") in t:
            return "A", kw
    for kw in TIER_B:
        if kw.replace(" ", "") in t:
            return "B", kw
    for head in TIER_C_HEAD:
        if head in t and any(tail in t for tail in TIER_C_TAIL):
            return "C", head
    return None, None


# ---------------------------------------------------------------- 공통 호출

def call(endpoint, params, retries=3):
    backoffs = [2, 5, 10]
    for i in range(retries):
        try:
            r = requests.get(endpoint, params=params, timeout=45)
            body = r.text
            if not body.lstrip().startswith("{"):
                print(f"  [!] JSON이 아닌 응답 (앞 400자):\n{body[:400]}\n")
                return None
            return r.json()
        except Exception as e:
            wait = backoffs[min(i, len(backoffs) - 1)]
            print(f"  [!] 시도 {i+1} 실패: {e}  ({wait}초 대기 후 재시도)")
            time.sleep(wait)
    return None


def items_of(payload):
    if not payload:
        return []
    body = payload.get("response", {}).get("body", {})
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items or []


def total_of(payload):
    if not payload:
        return 0
    return payload.get("response", {}).get("body", {}).get("totalCount", 0)


def fetch_list_page(bgn, end, page=1, rows=500):
    params = {
        "serviceKey": SERVICE_KEY,
        "inqryDiv": "1",
        "type": "json",
        "inqryBgnDt": bgn,
        "inqryEndDt": end,
        "pageNo": page,
        "numOfRows": rows,
    }
    return call(LIST_ENDPOINT, params)


TITLE_KEY = "bidNtceNm"
NO_KEY = "bidNtceNo"
ORD_KEY = "bidNtceOrd"
ORG_KEY = "ntceInsttNm"
DEMAND_KEY = "dminsttNm"
DATE_KEY = "bidNtceDt"
AMT_KEY = "asignBdgtAmt"
FILE_URL_KEYS = [f"ntceSpecDocUrl{i}" for i in range(1, 11)]
FILE_NAME_KEYS = [f"ntceSpecFileNm{i}" for i in range(1, 11)]


# ---------------------------------------------------------------- 1. probe

def cmd_probe():
    if not SERVICE_KEY:
        print("G2B_SERVICE_KEY 가 비어 있습니다. .env 파일을 확인하십시오."); return

    bgn, end = "202608010000", "202608012359"
    print(f"=== 목록 API 호출: {LIST_ENDPOINT}")
    payload = fetch_list_page(bgn, end, rows=3)
    items = items_of(payload)
    if not items:
        print("  → 레코드 없음 또는 실패."); print(payload); return

    print(f"  → 성공. totalCount = {total_of(payload)}")
    rec = items[0]
    print(f"\n  [필드 {len(rec)}개]")
    for k in sorted(rec.keys()):
        print(f"    {k:30s} = {str(rec[k])[:70]}")

    (OUT / "probe_list_fields.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {OUT/'probe_list_fields.json'} 저장 완료")


# ---------------------------------------------------------------- 2. collect (재개 지원)

def month_windows(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    while (y, m) <= (ey, em):
        last = 31
        while True:
            try:
                datetime(y, m, last); break
            except ValueError:
                last -= 1
        yield f"{y}{m:02d}", f"{y}{m:02d}010000", f"{y}{m:02d}{last}2359"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"done_months": []}


def save_progress(progress):
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def load_matched():
    if MATCHED_PATH.exists():
        return json.loads(MATCHED_PATH.read_text(encoding="utf-8"))
    return []


def save_matched(matched):
    MATCHED_PATH.write_text(json.dumps(matched, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_collect(start_ym="202601", end_ym="202608", restart=False):
    if not SERVICE_KEY:
        print("G2B_SERVICE_KEY 가 비어 있습니다. .env 파일을 확인하십시오."); return

    if restart:
        progress = {"done_months": []}
        matched_all = []
        print("[안내] --restart 지정됨 — 기존 진행 기록을 무시하고 처음부터 시작합니다.")
    else:
        progress = load_progress()
        matched_all = load_matched()
        if progress["done_months"]:
            print(f"[안내] 이전 진행 기록 발견 — 완료된 달: {progress['done_months']}")
            print(f"       기존 매칭 {len(matched_all)}건에 이어서 진행합니다.")

    print(f"수집 범위: {start_ym} ~ {end_ym}")
    calls_this_run = 0
    scanned_this_run = 0
    t0 = time.time()

    for ym, bgn, end in month_windows(start_ym, end_ym):
        if ym in progress["done_months"]:
            print(f"  [{ym}] 이미 완료됨 — 건너뜀")
            continue

        page = 1
        month_scanned = 0
        month_start = time.time()
        while True:
            payload = fetch_list_page(bgn, end, page=page, rows=500)
            calls_this_run += 1
            items = items_of(payload)
            if not items:
                break
            n = len(items)
            scanned_this_run += n
            month_scanned += n
            for rec in items:
                title = str(rec.get(TITLE_KEY, ""))
                tier, kw = classify(title)
                if tier:
                    rec["_tier"], rec["_keyword"] = tier, kw
                    matched_all.append(rec)
            total = total_of(payload)
            elapsed = time.time() - t0
            print(f"    [{ym}] 페이지 {page} — 이 달 {month_scanned}/{total} / "
                  f"전체 매칭 {len(matched_all)}건 / 이번 실행 경과 {elapsed:.0f}초")
            if page * 500 >= int(total or 0):
                break
            page += 1
            time.sleep(0.5)

        # 한 달 끝날 때마다 즉시 저장 — 중단돼도 이 시점까지는 안전
        progress["done_months"].append(ym)
        save_progress(progress)
        save_matched(matched_all)
        month_elapsed = time.time() - month_start
        print(f"  >> {ym} 완료 및 저장됨 — 이 달 소요 {month_elapsed:.0f}초 / "
              f"전체 매칭 누적 {len(matched_all)}건\n")

    print(f"\n=== 이번 실행 요약 ===")
    print(f"  이번 실행에서 스캔  : {scanned_this_run:,}건")
    print(f"  이번 실행 API 호출 : {calls_this_run}회")
    print(f"  전체 누적 매칭      : {len(matched_all):,}건")
    tiers = Counter(r["_tier"] for r in matched_all)
    for t in "ABC":
        print(f"    Tier {t}: {tiers.get(t,0):,}건")
    print(f"\n  → {MATCHED_PATH} 에 누적 저장되어 있습니다.")

    all_target_months = [ym for ym, _, _ in month_windows(start_ym, end_ym)]
    if all(m in progress["done_months"] for m in all_target_months):
        print(f"\n  모든 대상 기간({start_ym}~{end_ym}) 수집이 완료되었습니다.")
    else:
        remaining = [m for m in all_target_months if m not in progress["done_months"]]
        print(f"\n  남은 달: {remaining} — 같은 명령을 다시 실행하면 이어서 진행됩니다.")


# ---------------------------------------------------------------- 3. audit

def cmd_audit(sample_n=30):
    import random
    if not MATCHED_PATH.exists():
        print("matched.json 이 없습니다. collect 를 먼저 실행하십시오."); return

    recs = json.loads(MATCHED_PATH.read_text(encoding="utf-8"))
    if not recs:
        print("매칭된 공고가 0건입니다. collect 결과를 확인하십시오."); return

    random.seed(42)
    sample = random.sample(recs, min(sample_n, len(recs)))

    has_file, ext_counter, rows = 0, Counter(), []
    for rec in sample:
        names = []
        for uk, nk in zip(FILE_URL_KEYS, FILE_NAME_KEYS):
            u, n = rec.get(uk), rec.get(nk)
            if u and str(u).strip():
                names.append(str(n or ""))
        if names:
            has_file += 1
        for name in names:
            ext = Path(name).suffix.lower().strip(".") or "unknown"
            ext_counter[ext] += 1

        rows.append({
            "공고번호": rec.get(NO_KEY),
            "공고명": str(rec.get(TITLE_KEY, ""))[:60],
            "기관": rec.get(ORG_KEY),
            "티어": rec.get("_tier"),
            "첨부수": len(names),
            "파일명": " | ".join(names)[:150],
        })

    print(f"\n=== 첨부 감사 (표본 {len(sample)}건)")
    print(f"  첨부파일 있는 공고 : {has_file}/{len(sample)}  ({has_file/len(sample)*100:.0f}%)")
    print(f"\n  [포맷 분포]")
    for ext, c in ext_counter.most_common():
        print(f"    {ext:10s} {c:4d}건")

    import csv
    with open(OUT / "audit_sample.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\n  → {OUT/'audit_sample.csv'} 저장 완료")


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "collect":
        args = [a for a in sys.argv[2:] if not a.startswith("--")]
        restart = "--restart" in sys.argv[2:]
        if len(args) >= 2:
            cmd_collect(args[0], args[1], restart=restart)
        else:
            cmd_collect(restart=restart)
    elif cmd == "probe":
        cmd_probe()
    elif cmd == "audit":
        cmd_audit()
    else:
        print(f"알 수 없는 명령: {cmd}")
        print("사용 가능: probe / collect [시작YYYYMM] [종료YYYYMM] [--restart] / audit")