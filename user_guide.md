# RPG Maker 번역 자동화 시스템 사용자 가이드

이 문서는 RPG Maker 게임의 일본어 텍스트를 추출하고, AI로 번역한 후, 다시 게임에 적용하는 전체 과정을 설명합니다.

---

## 0. 사전 준비 (Prerequisites)

### 0.1. 환경 설정
*   **Python 3.10 이상**이 설치되어 있어야 합니다.
*   터미널(CMD, PowerShell)에서 다음 명령어로 필수 라이브러리를 설치하세요.
    ```bash
    pip install aiohttp
    ```
    *(시스템 구동에 필요한 비동기 통신 라이브러리입니다)*

### 0.2. 설정 파일 확인
*   `trans4/config/config.json` 파일을 열어 다음 항목을 확인하세요.
    *   `GEMINI_API_KEY`: Google Gemini API 키가 올바르게 입력되어 있어야 합니다.
    *   `MODEL_NAME`: 사용할 모델명 (예: `gemini-pro`, `gemini-1.5-flash` 등).

---

## 1. 추출 (Extraction) 단계

게임 데이터 파일에서 일본어 텍스트만 뽑아내는 과정입니다.

### 실행 명령어
```bash
python trans4/01_extract/extractor.py --data-dir "새 폴더" --output-dir "trans4/output"
```

### 파라미터 설명
*   `--data-dir`: 원본 게임 데이터(`Map*.json`, `CommonEvents.json` 등)가 들어있는 폴더 경로입니다. (예: `새 폴더`, `data` 등)
*   `--output-dir`: 추출된 결과물이 저장될 폴더입니다.

### 결과 확인
`trans4/output/` 폴더에 다음 파일들이 생성되었는지 확인하세요.
*   `japanese_texts.txt`: 번역할 일반 대사들이 들어있습니다.
*   `japanese_risky.txt`: 스크립트나 주석 등 주의가 필요한 텍스트입니다.
*   `mapping.json`: 나중에 번역문을 게임에 다시 넣을 때 필요한 '지도' 파일입니다.

---

## 2. 번역 (Translation) 단계

추출된 텍스트를 AI에게 보내 한국어로 번역하는 과정입니다.

### 실행 명령어
```bash
python trans4/02_translate/run_translation.py
```
*(또는 `python trans4/02_translate/translator.py --input-file "trans4/output/japanese_texts.txt"`)*

### 토큰 절약 방식 (v3)
*   LLM에는 제어문자(`\F[...]`, `\AA[...]`, `\|`, `\!` 등)를 뺀 **순수 문장만** 보냅니다. 태그는 `text_codec.py`가 번역 후 코드로 복원하므로 저가 모델이 태그를 망가뜨릴 수 없습니다.
*   문장 중간의 `\V[n]`, `%1` 같은 값은 `{1}`로 바꿔 보내고, 번역문에서 빠지면 그 줄만 다시 요청합니다.
*   같은 문장은 한 번만 번역하고, `glossary.json`의 `고정_번역`과 정확히 일치하는 줄은 LLM을 거치지 않습니다.
*   요청 형식은 JSON 대신 `ID|화자|원문` 한 줄 형식이며, 응답도 `ID|번역`만 받습니다.
*   `translation_settings.max_concurrent` 만큼 동시에 요청합니다.

### 진행 상황 / 이어하기
*   번역된 문장은 `output/translated_texts.cache.json`에 계속 저장됩니다. 중간에 끊겨도 다시 실행하면 캐시된 문장은 건너뜁니다.
*   끝까지 실패한 줄은 원문을 유지하고 `output/translated_texts.failed.jsonl`에 사유와 함께 기록됩니다.
*   `--dry-run` 옵션으로 API 호출 없이 실제로 전송될 프롬프트를 확인할 수 있습니다.
*   API 키는 `config.json`에 넣거나 환경변수(`DEEPSEEK_API_KEY` 등)로 지정합니다.

### 결과 확인
*   `output/translated_texts.txt`에 원본과 같은 순서·같은 줄 수로 저장됩니다.

---

## 3. 병합 (Merge) 단계

번역된 한국어 텍스트를 게임 파일에 넣는 과정입니다. **원본 폴더는 수정하지 않고**, 지정한 출력 폴더에 번역이 적용된 복사본을 만듭니다.

### 실행 명령어
```bash
python 03_merge/merger.py --data-dir "원본_data_폴더" --output-dir "번역본/data"
```

### 파라미터 설명
*   `--data-dir`: 원본 게임 데이터 폴더입니다. 읽기만 합니다.
*   `--output-dir`: 번역이 적용된 data 폴더가 만들어질 위치입니다. 원본 폴더와 같으면 실행을 거부합니다.
*   `--mapping`: 기본값 `output/mapping.json`
*   `--translations`: 기본값 `output/translated_texts.txt`. risky 번역본이 있으면 뒤에 함께 적습니다.
*   `--include-risky`: 스크립트·주석 등 risky 번역도 적용합니다. (기본은 제외)

### 안전장치
*   번역 줄과 매핑을 `line_index`로 1:1 연결합니다. 번역 파일 줄 수나 `page_id`가 맞지 않으면 **아무것도 쓰지 않고 중단**합니다.
*   적용 직전에 게임 파일의 원문이 추출 당시(`original_key`)와 같은지 확인합니다. 게임이 업데이트되어 원문이 바뀐 곳은 건너뜁니다.
*   번역문의 제어문자(모양·개수·순서)가 원문과 하나라도 다르면 그 줄은 적용하지 않습니다.
*   `note`, `faceName` 같은 파일명·플러그인 설정 경로는 적용하지 않습니다.
*   건너뛴 줄은 `output/merge_report.jsonl`에 사유와 함께 기록됩니다.

### 결과 확인
*   출력 폴더의 data를 게임 폴더의 data와 바꿔 넣고 게임(Game.exe)을 실행해 확인합니다.

---

## 4. 정리 (Cleanup) 단계

새로운 번역 작업을 시작하거나, `trans4/output` 폴더를 깨끗하게 비우고 싶을 때 사용합니다. 이전 작업의 잔여물이 다음 작업에 영향을 주지 않도록 할 때 유용합니다.

### 실행 명령어
```bash
python trans4/clean_output.py
```
*(또는 `python trans4/clean_output.py -y` 명령어로 확인 절차 없이 즉시 삭제할 수 있습니다.)*

### 기능 및 주의사항
*   `trans4/output` 폴더 내의 **모든 파일과 하위 폴더**(`japanese_texts.txt`, `mapping.json`, 번역된 텍스트 파일 등)를 삭제합니다.
*   실행 시 실수로 지우는 것을 방지하기 위해 **삭제 여부를 묻는 확인 메시지(`y/n`)**가 표시됩니다.
*   **주의**: 아직 병합하지 않은 번역 결과물이 있다면 백업 후 실행하세요. 삭제된 파일은 복구할 수 없습니다.

---

## 5. 트러블슈팅 (Troubleshooting)

### Q1. `ModuleNotFoundError: No module named 'aiohttp'` 오류가 떠요.
*   **해결**: `pip install aiohttp` 명령어를 터미널에 입력하여 라이브러리를 설치해주세요.

### Q2. 추출된 텍스트가 너무 적어요 / 이상해요.
*   **해결**: `trans4/01_extract/extractor.py`의 정규식 설정이나 `mapping.json`을 확인해야 합니다. 개발자에게 문의하거나 `japanese_risky.txt`를 확인해보세요.

### Q3. 번역 중 API 에러가 계속 발생해요.
*   **해결**: `config.json`의 API 키가 유효한지 확인하거나, 할당량(Quota)을 초과했는지 확인하세요. 잠시 후 다시 시도해보세요.

### Q4. 게임 실행 시 "SyntaxError" 또는 검은 화면이 떠요.
*   **해결**: 번역 과정에서 제어 문자(`\C[0]`, `\V[1]` 등)가 깨졌거나, 스크립트 코드(`risky` 항목)를 잘못 건드린 경우입니다. 백업한 원본으로 복구하고, `japanese_risky.txt` 내용을 제외하거나 검수 후 병합하세요.
