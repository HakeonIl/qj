"""
RPG Maker 게임 텍스트 추출기 v4 (스마트 추출 & 재귀 탐색)
일본어 판별 로직 강화 및 재귀적 데이터 탐색 기능 추가
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any


class SmartTextExtractor:
    def __init__(self, skip_names=False, maps_only=False):
        self.global_line_index = 0
        self.mappings = []
        self.skip_names = skip_names
        self.maps_only = maps_only
        
        # 화자 추적을 위한 상태
        self.current_speaker = None
        
        # 일본어 정규식 컴파일 (성능 최적화)
        # 히라가나: \u3040-\u309F
        # 가타카나: \u30A0-\u30FF
        # CJK 통합 한자 (기본): \u4E00-\u9FFF
        # CJK 통합 한자 (확장 A): \u3400-\u4DBF
        # CJK 통합 한자 (확장 B): \u20000-\u2A6DF (파이썬 정규식에서 지원 범위 확인 필요, 보통 됨)
        # 반각 가타카나: \uFF61-\uFF9F
        # 일본어 문장 부호: 、 。 「 」 ・
        
        # \u20000 이상은 서로게이트 페어 문제로 처리가 복잡할 수 있으나 파이썬 3은 잘 처리함.
        # 그러나 안전을 위해 기본+확장A+반각+기호 위주로 구성.
        self.jp_pattern = re.compile(
            r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\uFF61-\uFF9F、。「」・]'
        )
        
    def has_japanese(self, text: str) -> bool:
        """강력해진 일본어 포함 여부 확인"""
        if not text or not isinstance(text, str) or len(text.strip()) == 0:
            return False
            
        return bool(self.jp_pattern.search(text))

    def extract_text_from_parameters(self, params: list, cmd_code: int) -> Optional[Any]:
        """명령어 코드에 따라 텍스트 추출"""
        try:
            # code 401: 메시지 대화 (대사 내용)
            if cmd_code == 401 and len(params) > 0:
                return (None, str(params[0]), "dialog")
            
            # code 101: 메시지 설정 (화자 이름)
            elif cmd_code == 101 and len(params) > 4:
                name = str(params[4]).strip()
                if name:
                    return (None, name, "name")
            
            # code 102: 선택지
            elif cmd_code == 102 and len(params) > 0:
                choices = params[0]
                if isinstance(choices, list):
                    return [(None, str(choice), "choice") for choice in choices]
            
            # code 405: 크레딧
            elif cmd_code == 405 and len(params) > 0:
                return (None, str(params[0]), "credit")
            
            # === Risky Extraction (위험 요소 추출) ===
            # 오작동 위험이 있는 코드들도 추출 (별도 타입 'risky' 지정)
            
            # code 355, 655: 스크립트
            elif cmd_code in [355, 655] and len(params) > 0:
                return (None, str(params[0]), "risky_script")
                
            # code 356: 플러그인 명령 (MV)
            # code 357: 플러그인 명령 (MZ)
            elif cmd_code in [356, 357] and len(params) > 0:
                 # 플러그인 명령 전체가 텍스트일 수도 있고, 인자 중 일부일 수도 있음.
                 # 일단 전체를 추출하되, has_japanese로 필터링됨.
                 if len(params) >= 4 and cmd_code == 357: # MZ 구조: file, name, ext, args
                     # args가 딕셔너리거나 리스트일 수 있음. 복잡하므로 args 전체를 문자열로 변환하여 검사?
                     # 일단 357은 구조가 복잡하여 제외하거나 단순 문자열만 추출.
                     # parameter[3]이 args
                     pass
                 elif cmd_code == 356: # MV 구조: string
                     return (None, str(params[0]), "risky_plugin")

            # code 320: 이름 입력 처리 (Name Input Processing) - 캐릭터 이름 변경 등
            # code 324: 별명 변경 (Change Nickname)
            elif cmd_code in [320, 324]:
                 # 파라미터 구조 확인 필요하나, 보통 직접 텍스트를 입력받는게 아니라 ID 참조임.
                 # 320: [actorId, maxChars] -> 텍스트 없음
                 # 324: [actorId, nickname] -> 닉네임 텍스트 있음
                 if cmd_code == 324 and len(params) > 1:
                     return (None, str(params[1]), "risky_system")

            # code 108, 408: 주석 (Comment)
            # 주석은 번역해도 게임에 영향 없지만, 개발자 메모일 수 있음.
            # risky로 분류하여 추출
            elif cmd_code in [108, 408] and len(params) > 0:
                 return (None, str(params[0]), "risky_comment")
                 
            # code 118: Label (라벨)
            # 라벨 이름은 내부적으로 점프할 때 쓰이므로 번역하면 안 될 수도 있지만,
            # 텍스트로 표시되는 경우도 있으니 risky로 분류
            elif cmd_code == 118 and len(params) > 0:
                 return (None, str(params[0]), "risky_system")
                 
        except Exception:
            pass
        
        return None
    
    def process_event_commands(self, commands: list, page_id: str, 
                           source_file: str, base_path: str) -> List[Tuple[str, str, str]]:
        """이벤트 명령어 리스트에서 텍스트 추출"""
        texts = []
        
        for idx, cmd in enumerate(commands):
            if not isinstance(cmd, dict):
                continue
            
            code = cmd.get('code', 0)
            params = cmd.get('parameters', [])
            
            result = self.extract_text_from_parameters(params, code)
            
            if result is None:
                continue
            
            # 복수 결과 (선택지 등)
            if isinstance(result, list):
                for choice_idx, item in enumerate(result):
                    if item and len(item) == 3:
                        speaker, text, text_type = item
                        if self.has_japanese(text):
                            texts.append((speaker, text, text_type))
                            
                            # 검증을 위한 원본 키 (최대 10자)
                            original_key = text[:10] if text else ""
                            
                            self.mappings.append({
                                "line_index": self.global_line_index,
                                "page_id": page_id,
                                "line_in_page": len(texts) - 1,
                                "source_file": source_file,
                                "json_path": f"{base_path}.list[{idx}].parameters[0][{choice_idx}]",
                                "original_key": original_key, # 검증용 키 추가
                                "command_code": code
                            })
                            self.global_line_index += 1
            else:
                speaker, text, text_type = result
                
                # 화자 이름 (이름도 번역 대상)
                if text_type == "name":
                    self.current_speaker = text
                    if self.has_japanese(text):
                        texts.append((None, text, "name"))
                        
                        original_key = text[:10] if text else ""
                        
                        self.mappings.append({
                            "line_index": self.global_line_index,
                            "page_id": page_id,
                            "line_in_page": len(texts) - 1,
                            "source_file": source_file,
                            "json_path": f"{base_path}.list[{idx}].parameters[4]",
                            "original_key": original_key,
                            "command_code": code
                        })
                        self.global_line_index += 1
                
                # 대사, 크레딧, 그리고 Risky 텍스트들
                elif text_type in ["dialog", "credit"] or str(text_type).startswith("risky_"):
                    if self.has_japanese(text):
                        texts.append((self.current_speaker, text, text_type))
                        
                        original_key = text[:10] if text else ""
                        
                        # 파라미터 인덱스 결정 (기본값 0)
                        param_idx = 0
                        if code == 324: # 별명 변경은 인덱스 1
                            param_idx = 1
                        
                        self.mappings.append({
                            "line_index": self.global_line_index,
                            "page_id": page_id,
                            "line_in_page": len(texts) - 1,
                            "source_file": source_file,
                            "json_path": f"{base_path}.list[{idx}].parameters[{param_idx}]",
                            "original_key": original_key, # 검증용 키 추가
                            "command_code": code
                        })
                        self.global_line_index += 1
        
        return texts
    
    def extract_recursive(self, data: Any, source_file: str, current_path: str, page_id: str) -> List[Tuple[Optional[str], str, str]]:
        """재귀적으로 JSON 구조를 탐색하여 모든 문자열 추출 (System.json 등 사용)"""
        texts = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{current_path}.{key}"
                # 키 이름에 '.'이 포함된 경우 처리 (["key.name"] 형태가 되어야 함)
                # 여기서는 단순화를 위해 표준 점 표기법 사용하되, 특수 문자는 주의 필요
                # 하지만 RPG Maker 데이터 구조상 키는 보통 식별자임.
                
                if isinstance(value, str):
                    if self.has_japanese(value):
                        texts.append((None, value, "system_recursive"))
                        
                        original_key = value[:10] if value else ""
                        
                        self.mappings.append({
                            "line_index": self.global_line_index,
                            "page_id": page_id,
                            "line_in_page": len(texts) - 1,
                            "source_file": source_file,
                            "json_path": f"{new_path}", # $.terms.messages.save 등
                            "original_key": original_key,
                            "command_code": 0
                        })
                        self.global_line_index += 1
                elif isinstance(value, (dict, list)):
                    texts.extend(self.extract_recursive(value, source_file, new_path, page_id))
                    
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                new_path = f"{current_path}[{idx}]"
                
                if isinstance(value, str):
                    if self.has_japanese(value):
                        texts.append((None, value, "system_recursive"))
                        
                        original_key = value[:10] if value else ""
                        
                        self.mappings.append({
                            "line_index": self.global_line_index,
                            "page_id": page_id,
                            "line_in_page": len(texts) - 1,
                            "source_file": source_file,
                            "json_path": f"{new_path}",
                            "original_key": original_key,
                            "command_code": 0
                        })
                        self.global_line_index += 1
                elif isinstance(value, (dict, list)):
                    texts.extend(self.extract_recursive(value, source_file, new_path, page_id))
                    
        return texts

    def extract_map_file(self, map_path: Path, map_num: int) -> List[Dict]:
        """맵 파일 추출"""
        pages_data = []
        
        try:
            with open(map_path, 'r', encoding='utf-8') as f:
                map_data = json.load(f)
            
            events = map_data.get('events', [])
            
            for event_idx, event in enumerate(events):
                if event is None:
                    continue
                
                event_id = event.get('id', 0)
                event_name = event.get('name', '')
                pages = event.get('pages', [])
                
                # 맵 이벤트 이름 추출 (옵션) - 플러그인 등에서 사용될 수 있음
                if not self.skip_names and self.has_japanese(event_name):
                    # 별도 페이지로 취급하기보다 별도 타입으로 저장
                    # 하지만 구조상 복잡해지므로 여기서는 생략하고 본문만 집중.
                    pass
                
                for page_idx, page in enumerate(pages):
                    page_id = f"map{map_num:03d}_ev{event_id}_p{page_idx}"
                    commands = page.get('list', [])
                    
                    self.current_speaker = event_name
                    
                    texts = self.process_event_commands(
                        commands, page_id, f"Map{map_num:03d}.json", 
                        f"$.events[{event_idx}].pages[{page_idx}]"
                    )
                    
                    if texts:
                        pages_data.append({
                            "page_id": page_id,
                            "event_name": event_name,
                            "lines": texts
                        })
        except Exception as e:
            print(f"Error processing {map_path}: {e}")
        
        return pages_data
    
    def extract_common_events(self, common_path: Path) -> List[Dict]:
        """커먼 이벤트 추출"""
        pages_data = []
        try:
            with open(common_path, 'r', encoding='utf-8') as f:
                common_events = json.load(f)
            
            for event_idx, event in enumerate(common_events):
                if event is None:
                    continue
                
                event_id = event.get('id', 0)
                event_name = event.get('name', '')
                commands = event.get('list', [])
                
                page_id = f"common{event_id:03d}"
                
                self.current_speaker = event_name
                
                texts = self.process_event_commands(
                    commands, page_id, "CommonEvents.json", f"$[{event_idx}]"
                )
                
                if texts:
                    pages_data.append({
                        "page_id": page_id,
                        "event_name": event_name,
                        "lines": texts
                    })
        except Exception as e:
            print(f"Error processing CommonEvents: {e}")
        
        return pages_data
        
    def extract_system_recursive(self, data_dir: Path) -> List[Dict]:
        """System.json 완전 재귀 추출"""
        system_pages = []
        system_path = data_dir / "System.json"
        
        if not system_path.exists():
            return system_pages
            
        try:
            with open(system_path, 'r', encoding='utf-8') as f:
                system_data = json.load(f)
            
            # 재귀적으로 모든 문자열 추출
            # page_id는 하나로 통일
            page_id = "system_full_recursive"
            
            texts = self.extract_recursive(system_data, "System.json", "$", page_id)
            
            # 필터링: 이미 추출된 값 중 "sounds", "images" 등 파일 경로처럼 보이는 것은 제외하는 로직 추가 가능
            # 하지만 has_japanese가 꽤 강력하므로 믿고 감.
            
            if texts:
                system_pages.append({
                    "page_id": page_id,
                    "event_name": "System",
                    "lines": texts
                })
                
        except Exception as e:
            print(f"Error processing System.json: {e}")
            
        return system_pages

    def extract_static_data(self, data_dir: Path) -> List[Dict]:
        """정적 데이터 추출 (Items, Actors, etc.)"""
        static_pages = []
        
        # System.json (재귀)
        static_pages.extend(self.extract_system_recursive(data_dir))
        
        # 나머지 파일들 (Items, Actors, etc.)
        files_to_scan = [
            ("Items.json", "static_items", "Items"),
            ("Actors.json", "static_actors", "Actors"),
            ("Weapons.json", "static_weapons", "Weapons"),
            ("Armors.json", "static_armors", "Armors"),
            ("Skills.json", "static_skills", "Skills"),
            ("States.json", "static_states", "States"),
            ("Classes.json", "static_classes", "Classes"),
            ("Enemies.json", "static_enemies", "Enemies"),
            ("Troops.json", "static_troops", "Troops") # Troops도 정적 데이터처럼 취급 (단순화)
        ]
        
        for filename, page_prefix, event_name in files_to_scan:
            file_path = data_dir / filename
            if not file_path.exists():
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 재귀적으로 추출 시도
                # 각 파일마다 하나의 거대한 페이지로 만듦 (관리 용이성)
                texts = self.extract_recursive(data, filename, "$", page_prefix)
                
                if texts:
                    static_pages.append({
                        "page_id": page_prefix,
                        "event_name": event_name,
                        "lines": texts
                    })
                    
            except Exception as e:
                print(f"Error processing {filename}: {e}")
        
        return static_pages

    def extract_all(self, data_dir: Path, output_dir: Path):
        """전체 추출 실행"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        all_pages = []
        
        # 1. Map Files
        map_files = sorted(data_dir.glob("Map[0-9]*.json"))
        print(f"Scanning {len(map_files)} map files...")
        for map_file in map_files:
            # MapInfos.json 처리 추가 (MapInfos는 맵 이름 정보를 담고 있음)
            if map_file.stem == "MapInfos": 
                continue # 아래에서 별도 처리
                
            map_num = int(map_file.stem[3:])
            all_pages.extend(self.extract_map_file(map_file, map_num))
            
        # 1-1. MapInfos.json
        map_infos_path = data_dir / "MapInfos.json"
        if map_infos_path.exists():
            print("Scanning MapInfos.json...")
            try:
                with open(map_infos_path, 'r', encoding='utf-8') as f:
                    map_infos_data = json.load(f)
                
                # MapInfos는 리스트 형태이며 각 항목이 맵 정보 객체임
                map_infos_texts = self.extract_recursive(map_infos_data, "MapInfos.json", "$", "MapInfos")
                
                if map_infos_texts:
                    all_pages.append({
                        "page_id": "MapInfos",
                        "event_name": "MapNames",
                        "lines": map_infos_texts
                    })
            except Exception as e:
                print(f"Error processing MapInfos.json: {e}")
            
        # 2. Common Events
        common_path = data_dir / "CommonEvents.json"
        if common_path.exists():
            print("Scanning CommonEvents...")
            all_pages.extend(self.extract_common_events(common_path))
            
        # 3. Static Data (System, Items, etc.)
        if not self.maps_only:
            print("Scanning static data (recursive)...")
            all_pages.extend(self.extract_static_data(data_dir))
            
        # 4. 저장 (일반 텍스트와 Risky 텍스트 분리)
        print(f"Saving extracted text to {output_dir}...")
        
        normal_count = 0
        risky_count = 0
        
        with open(output_dir / "japanese_texts.txt", 'w', encoding='utf-8') as f_normal, \
             open(output_dir / "japanese_risky.txt", 'w', encoding='utf-8') as f_risky:
            
            for page in all_pages:
                for speaker, text, text_type in page["lines"]:
                    json_line = {
                        "page_id": page["page_id"],
                        "speaker": speaker,
                        "text": text,
                        "type": text_type
                    }
                    line_str = json.dumps(json_line, ensure_ascii=False) + "\n"
                    
                    if str(text_type).startswith("risky_"):
                        f_risky.write(line_str)
                        risky_count += 1
                    else:
                        f_normal.write(line_str)
                        normal_count += 1
                    
        # mapping.json
        mapping_data = {
            "metadata": {
                "total_lines": self.global_line_index,
                "total_pages": len(all_pages),
                "extractor_version": "v4_smart",
                "normal_lines": normal_count,
                "risky_lines": risky_count
            },
            "mappings": self.mappings
        }
        
        with open(output_dir / "mapping.json", 'w', encoding='utf-8') as f:
            json.dump(mapping_data, f, ensure_ascii=False, indent=2)
            
        print(f"✓ Extraction complete!")
        print(f"  - Normal texts: {normal_count} lines (saved to japanese_texts.txt)")
        print(f"  - Risky texts : {risky_count} lines (saved to japanese_risky.txt)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='RPG Maker Smart Text Extractor v4')
    parser.add_argument('--data-dir', required=True, help='Data directory path')
    parser.add_argument('--output-dir', required=True, help='Output directory path')
    parser.add_argument('--maps-only', action='store_true', help='Extract only map files')
    
    args = parser.parse_args()
    
    extractor = SmartTextExtractor(maps_only=args.maps_only)
    extractor.extract_all(Path(args.data_dir), Path(args.output_dir))

if __name__ == "__main__":
    main()
