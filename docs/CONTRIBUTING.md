# CONTRIBUTING — Phase 1 담당자 온보딩 가이드

이 문서는 이 저장소(`korea-public-erp-rfp-analysis`)에 처음 합류하는
팀원을 위한 것입니다. 담당 범위는 **Phase 1: 다운로드·텍스트 추출** 입니다.

---

## 1. 프로젝트 한 줄 요약

한국 공공기관의 나라장터 입찰공고 중 ERP 관련 제안요청서(RFP)를 수집해,
요구사항을 항목 단위로 구조화하고 SAP 표준과의 갭을 분석하는 프로젝트입니다.

담당자는 이 중 **"공고 목록 → 실제 원문 텍스트"** 단계를 맡습니다.
뒤 단계(요구사항 구조화, SAP 갭 판정, 통계 분석, 문서화)는 프로젝트
오너가 진행하므로, 이 문서에 정의된 **출력 스펙만 정확히 지키면**
나머지는 신경 쓰지 않아도 됩니다.

---

## 2. 역할 구조 (실제 SE-딜리버리 협업 모델 재현)

- **SE 역할 (프로젝트 오너)**: 요구사항 분석, SAP 표준 갭 판정,
  파트너 커버리지 해석, 최종 제안 논리 — 프리세일즈가 실제로 소유하는 영역
- **Implementation 역할 (담당자)**: 데이터 추출·파이프라인 구축 —
  실무에서 딜리버리 엔지니어/파트너 SI가 담당하는 영역

---

## 3. 환경 준비

```powershell
git clone https://github.com/eugeejo-ui/korea-public-erp-rfp-analysis.git
cd korea-public-erp-rfp-analysis

pip install requests python-dotenv
pip install pyhwp pdfplumber odfpy
```

`.env` 파일은 저장소에 없습니다 (의도적으로 제외됨). Phase 1은 이미
수집된 `data/raw/phase0/matched.json`을 입력으로 쓰므로 API 키가
당장 필요 없습니다. 5년치로 범위를 확장해 재수집할 때만 별도로
`G2B_SERVICE_KEY`를 발급받아 `.env`에 넣으면 됩니다 (아래 8번 참고).

---

## 4. 작업 브랜치 생성

`main`에 직접 커밋하지 마십시오.

```powershell
git checkout -b feature/file-extraction
```

---

## 5. 입력 데이터

`data/raw/phase0/matched.json` — 8개월 표본으로 이미 수집된 1,427건의
공고 레코드입니다. 각 레코드에서 다음 필드를 씁니다.

| 필드 | 내용 |
|---|---|
| `bidNtceNo` | 공고번호 (출력 파일명에 사용) |
| `bidNtceNm` | 공고명 |
| `ntceSpecDocUrl1` ~ `ntceSpecDocUrl10` | 첨부파일 다운로드 URL (없으면 빈 문자열) |
| `ntceSpecFileNm1` ~ `ntceSpecFileNm10` | 첨부파일명 (확장자로 포맷 판단) |
| `_tier` | A/B/C — 키워드 매칭 신뢰도. C는 노이즈가 섞여 있을 수 있음 |

확인 명령어:

```powershell
python -c "import json; d = json.load(open('data/raw/phase0/matched.json', encoding='utf-8')); print(len(d), '건 확인됨')"
```

---

## 6. 만들어야 할 것 — `analysis/01_download_extract.py`

### 해야 하는 일

1. `matched.json`을 읽어 각 레코드의 첨부파일 URL을 순회
2. URL로 실제 파일 다운로드 (`data/raw/downloads/` 아래 임시 저장)
3. 확장자별로 텍스트 추출
   - `.hwp` → `pyhwp` (또는 `hwp5txt` 커맨드라인 활용)
   - `.pdf` → `pdfplumber`
   - `.odt` → `odfpy`
   - 그 외 확장자는 추출 시도하지 않고 로그에 "미지원 포맷"으로 기록
4. 다운로드나 추출이 실패해도 **전체를 멈추지 말고 해당 건만 로그에 남기고 계속 진행**
5. 재공고·정정공고로 인한 중복 공고번호는 최신 것 하나만 남기고 스킵

### 출력 스펙 (반드시 이 형식 — 뒤 단계가 이 형식을 그대로 읽습니다)

```
data/processed/extracted/{공고번호}.txt
```
- UTF-8 인코딩
- 파일 내용은 순수 추출 텍스트만 (다운로드 메타데이터, HTML 태그 등 섞지 않음)
- 한 공고에 첨부파일이 여러 개면 순서대로 이어붙이되, 파일 사이에
  구분선 한 줄(`\n--- 다음 첨부파일 ---\n`) 삽입

```
data/processed/extraction_log.csv
```
컬럼: `공고번호, 원본파일명, 상태(성공/실패/미지원포맷), 실패사유`

### 하지 말아야 할 것

- 다운로드 원본 파일(hwp, pdf 등)을 그대로 Git에 커밋하지 마십시오.
  용량이 크고 저작권 있는 문서 원문입니다. `data/raw/downloads/`는
  로컬에만 두고 `.gitignore`에 이미 등록되어 있는지 확인하십시오.
  없으면 아래 줄을 `.gitignore`에 추가하십시오.
  ```
  data/raw/downloads/
  ```
- `matched.json` 자체를 수정하지 마십시오. 읽기 전용 입력입니다.

---

## 7. 테스트 순서

전체(수천 건)를 한 번에 돌리기 전에 반드시 소규모로 먼저 검증하십시오.

```powershell
python analysis\01_download_extract.py --limit 10
```

`--limit` 인자를 스크립트 안에 직접 구현하십시오 (앞에서부터 N건만 처리).

10건 결과를 열어서 다음을 확인하십시오.
- 텍스트가 실제로 요구사항 내용을 담고 있는가 (깨진 문자, 빈 파일 아닌지)
- hwp/pdf/odt 세 포맷 모두 최소 1건씩은 테스트에 포함되었는가

문제없으면 전체 실행:

```powershell
python analysis\01_download_extract.py
```

---

## 8. (선택) 5년치로 수집 범위 확장

프로젝트 오너가 요청하는 경우에만 진행하십시오. 기존 8개월 표본 수집
스크립트(`analysis/00_phase0_probe.py`)를 재사용합니다.

```powershell
# .env에 G2B_SERVICE_KEY 설정 후
python analysis\00_phase0_probe.py collect 202101 202612
```

이 스크립트는 한 달 처리가 끝날 때마다 자동 저장되고, 중단 후 재실행하면
이어서 진행됩니다 (`phase0_out/collect_progress.json` 참고). 개발계정은
하루 호출 한도가 있으므로 하루 안에 안 끝나면 다음 날 같은 명령어로
이어서 실행하면 됩니다.

---

## 9. 커밋 및 PR

작은 단위로 자주 커밋하십시오.

```powershell
git add analysis/01_download_extract.py
git commit -m "Phase 1: 다운로드·추출 스크립트 초안"
git push origin feature/file-extraction
```

전체 실행 결과가 나오면:

```powershell
git add data/processed/extracted/ data/processed/extraction_log.csv
git commit -m "Phase 1: 추출 결과 (성공 N건 / 실패 M건)"
git push origin feature/file-extraction
```

완료되면 GitHub에서 `feature/file-extraction` → `main`으로
**Pull Request**를 생성하십시오. 직접 merge하지 말고 프로젝트
오너의 리뷰를 기다려 주십시오.

---

## 10. 막히면

- API/URL 관련 문제: `analysis/00_phase0_probe.py`의 `probe` 명령
  결과와 비교해보십시오. 필드명이 다르면 나라장터 API 응답 구조가
  바뀌었을 수 있습니다.
- 특정 hwp 파일이 계속 파싱 실패하면, 무리하게 해결하려 하지 말고
  `extraction_log.csv`에 실패로 기록하고 다음 건으로 넘어가십시오.
  실패율 자체가 Phase 0 게이트 판정에 참고되는 지표입니다.
