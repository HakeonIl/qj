# RPG Maker 번역 자동화 시스템 완전 분석 (v4)

본 문서는 RPG Maker 게임(MZ/MV)의 번역 자동화 시스템(Extractor, Translator, Merger)의 전체 동작 과정, 데이터 흐름, 파일 구조를 심층 분석한 기술 문서입니다.

## 1. 시스템 개요 (Architecture Overview)

이 시스템은 RPG Maker의 데이터 파일(`.json`)에서 텍스트를 **추출(Extract)**하고, LLM을 이용해 문맥을 고려하여 **번역(Translate)**한 뒤, 원본 게임 데이터 구조를 유지하며 다시 **병합(Merge)**하는 3단계 파이프라인으로 구성됩니다.

### 핵심 철학
1.  **데이터 무결성 (Integrity)**: 원본 게임 로직(스크립트 코드, 제어 문자 등)을 절대 훼손하지 않는다.
2.  **문맥 인식 (Context-Aware)**: 단순 문장 번역이 아니라, 화자(Speaker)와 상황을 고려하여 번역한다.
3.  **안전한 병합 (Safe Merge)**: JSONPath 매핑을 통해 원본 파일의 정확한 위치에 번역문을 삽입한다.

---

## 2. 모듈별 상세 분석

### 2.1. 추출기 (Extractor) - `trans4/01_extract/extractor.py`

게임 데이터에서 일본어 텍스트만을 정밀하게 찾아내어 번역 가능한 형태로 변환합니다.

#### 2.1.1. 작동 흐름
1.  **파일 스캔**: `data` 폴더(또는 지정된 원본 폴더) 내의 모든 `.json` 파일(`Map*.json`, `CommonEvents.json`, `System.json` 등)을 재귀적으로 탐색합니다.
2.  **이벤트 커맨드 파싱**: RPG Maker의 이벤트 커맨드 구조(`code`, `parameters`)를 분석합니다.
    *   **주요 타겟 코드**:
        *   `401` (대화): 일반 대사
        *   `102` (선택지): 플레이어 선택 옵션
        *   `101` (이름): 대화창에 표시되는 화자 이름
        *   `355, 655` (스크립트): `risky_script`로 분류 (특수 처리 필요)
        *   `108, 408` (주석): `risky_comment`로 분류 (개발자 메모 등)
3.  **일본어 필터링**: 정규식(`[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF...]`)을 사용하여 일본어가 포함된 텍스트만 추출합니다. (기호나 영어만 있는 시스템 코드는 제외)
4.  **매핑 데이터 생성**: 추출된 텍스트가 원본 파일의 *어디에* 위치하는지 정확한 주소(JSONPath)를 기록합니다.

#### 2.1.2. 출력 파일
*   **`japanese_texts.txt`**: 일반 번역 대상 (대사, 선택지 등). JSONL(JSON Lines) 포맷.
    ```json
    {"page_id": "map001_ev001_p0", "speaker": "미아", "text": "こんにちは。", "type": "dialog"}
    ```
*   **`japanese_risky.txt`**: 주의가 필요한 텍스트 (스크립트, 주석 등). 별도 검수나 특수 프롬프트 적용 가능.
*   **`mapping.json`**: 병합 시 사용될 핵심 지도.
    ```json
    {
      "mappings": [
        {
          "line_index": 0,
          "source_file": "Map001.json",
          "json_path": "$.events[1].pages[0].list[0].parameters[0]",
          "original_key": "こんにちは。"
        }
      ]
    }
    ```

---

### 2.2. 번역기 (Translator) - `trans4/02_translate/translator.py`

추출된 텍스트를 LLM(Gemini Pro 등)에게 전송하여 한국어로 번역합니다.

#### 2.2.1. 프롬프트 엔지니어링 전략 (`prompt_base_v2.md`)
*   **화자 정보 포함**: 단순 텍스트 나열이 아닌 `화자␟텍스트` 형식을 사용하여 AI가 누가 말하는지 이해하도록 합니다.
*   **제어 문자 보존**: `\C[0]`, `\V[1]` 등의 RPG Maker 제어 문자를 절대 삭제하거나 변경하지 않도록 강력히 지시합니다.
*   **용어집(Glossary) 적용**: `glossary.json`에 정의된 고유명사(캐릭터 이름, 지명 등)를 강제로 적용합니다.

#### 2.2.2. 배치 처리 및 재시도
1.  **청크(Chunk) 분할**: 수천 줄의 텍스트를 AI 컨텍스트 윈도우에 맞춰 적절한 크기(예: 50~100라인)로 자릅니다.
2.  **API 요청 및 검증**:
    *   입력 라인 수와 출력 라인 수가 일치하는지 확인.
    *   번역문에 포함된 제어 문자 개수가 원본과 크게 다르지 않은지 확인(Heuristic Check).
3.  **재시도 로직**: 검증 실패 시 해당 청크만 다시 번역을 시도하거나, 실패 로그(`failed_pages.json`)에 기록하여 나중에 별도 처리합니다.

#### 2.2.3. 입출력 데이터 흐름
*   **Input**: `japanese_texts.txt`
*   **Process**: LLM API (Prompt + Context)
*   **Output**: `trans4/output/korean_texts.txt` (또는 개별 청크 파일들)

---

### 2.3. 병합기 (Merger) - `trans4/03_merge/merger.py`

번역된 텍스트를 `mapping.json`을 참조하여 원본 게임 파일에 덮어씁니다.

#### 2.3.1. 작동 원리
1.  **원본 로드**: 원본 `data` 폴더의 JSON 파일들을 메모리에 로드합니다.
2.  **매핑 순회**: `mapping.json`의 각 항목을 순회합니다.
    *   `source_file`: 수정할 파일 식별 (예: `Map001.json`)
    *   `json_path`: 해당 파일 내의 수정할 위치 (예: `events[1].pages[0]...`)
    *   `line_index`: 번역문 리스트에서 몇 번째 라인을 가져올지 결정
3.  **데이터 주입 (Injection)**:
    *   JSONPath를 해석하여 해당 객체에 접근 (`object-path` 라이브러리 유사 로직 구현).
    *   원본 텍스트와 현재 텍스트(혹은 키값)를 비교하여 무결성 2차 검증(옵션).
    *   값을 번역된 한국어 텍스트로 교체.
4.  **파일 저장**: 수정된 JSON 객체를 원본 파일 경로(또는 별도 결과 폴더)에 덮어씁니다.

#### 2.3.2. 안전장치
*   **경로 검증**: JSONPath가 가리키는 곳이 실제로 존재하지 않으면 에러를 로깅하고 건너뜁니다(게임 크래시 방지).
*   **백업 권장**: 작업 전 원본 `data` 폴더의 백업은 필수입니다.

---

## 3. 전체 워크플로우 가이드

### 단계 1: 준비 (Preparation)
1.  `config/config.json` 설정 확인 (API 키, 모델명, 타겟 폴더 등).
2.  `config/glossary.json`에 주요 등장인물 및 용어 정의.

### 단계 2: 추출 (Extraction)
```bash
python trans4/01_extract/extractor.py --data-dir "원본_data_폴더" --output-dir "trans4/output"
```
*   결과 확인: `trans4/output/japanese_texts.txt`가 잘 생성되었는지 확인. `risky` 파일 내용 검토.

### 단계 3: 번역 (Translation)
```bash
python trans4/02_translate/translator.py --input-file "trans4/output/japanese_texts.txt"
```
*   중간 확인: `trans4/output/chunks/` 폴더에 번역된 텍스트 조각들이 생성되는지 모니터링.

### 단계 4: 병합 (Merging)
```bash
python trans4/03_merge/merger.py --base-dir "원본_data_폴더" --mapping-file "trans4/output/mapping.json" --translation-file "trans4/output/final_translated.txt"
```
*   최종 확인: RPG Maker 에디터나 게임을 실행하여 번역 적용 여부 및 오류 확인.

---

## 4. 폴더 구조 예시 (권장)

```
trans4/
├── 01_extract/
│   └── extractor.py        # 추출 스크립트
├── 02_translate/
│   ├── translator.py       # 번역 스크립트
│   └── prompt_base_v2.md   # 프롬프트 템플릿
├── 03_merge/
│   └── merger.py           # 병합 스크립트
├── config/
│   ├── config.json         # 전체 설정
│   └── glossary.json       # 용어집
└── output/                 # (자동 생성)
    ├── japanese_texts.txt  # 원본 텍스트
    ├── japanese_risky.txt  # 스크립트/주석 등
    ├── mapping.json        # 위치 매핑 데이터
    └── chunks/             # 번역 중간 결과물
```
