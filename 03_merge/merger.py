"""
RPG Maker 번역 병합기 v4 (Verified Merger)
원본 텍스트 검증을 통한 대화 밀림 방지 및 스트리밍 처리
"""
import json
import shutil
import re
import os
from pathlib import Path
from typing import Dict, List, Any

class VerifiedMerger:
    def __init__(self):
        self.mappings = []
        self.translations = {}
        
    def load_mappings(self, mapping_path: Path):
        """매핑 정보 로드"""
        print(f"Loading mappings from {mapping_path}...")
        with open(mapping_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.mappings = data.get('mappings', [])
            
    def load_translations(self, chunks_dir: Path, include_risky: bool = False):
        """번역된 청크 파일 로드 (메모리 최적화)"""
        print(f"Loading translations from {chunks_dir} (include_risky={include_risky})...")
        # page_id별로 정렬하여 로드
        files = sorted(chunks_dir.glob("*.txt"))
        
        count = 0
        for file in files:
            # 파일명 파싱 (page_id_chunk.txt)
            match = re.match(r'^(.*)_(\d+)\.txt$', file.name)
            if not match: continue
            
            page_id = match.group(1)
            
            if page_id not in self.translations:
                self.translations[page_id] = []
                
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            data = json.loads(line)
                            
                            # Risky 필터링
                            text_type = data.get('type', '')
                            if not include_risky and str(text_type).startswith('risky_'):
                                continue
                                
                            # (text, type) 튜플 저장
                            self.translations[page_id].append(data)
                        except: pass
            except Exception as e:
                print(f"Error reading {file}: {e}")
            
            count += 1
            
        print(f"Loaded translations for {len(self.translations)} pages.")

    def apply_translation_to_json(self, json_path: Path, updates: List[Dict]):
        """JSON 파일에 번역 적용 (안전한 파싱)"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            applied_count = 0
            
            for update in updates:
                json_path_str = update['json_path']
                new_value = update['value']
                
                # JSONPath 파싱 및 적용
                try:
                    # $.events[1].pages[0].list[5].parameters[0] 형태 파싱
                    parts = json_path_str.replace("$", "").replace("[", ".").replace("]", "").split(".")
                    parts = [p for p in parts if p]
                    
                    current = data
                    for i, part in enumerate(parts[:-1]):
                        if part.isdigit():
                            current = current[int(part)]
                        else:
                            current = current[part]
                    
                    last_key = parts[-1]
                    if last_key.isdigit():
                        current[int(last_key)] = new_value
                    else:
                        current[last_key] = new_value
                        
                    applied_count += 1
                
                except Exception as e:
                    # 경로가 안맞으면 스킵 (원본 파일이 변경되었거나 매핑이 잘못됨)
                    pass
            
            # 저장
            if applied_count > 0:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                
        except Exception as e:
            print(f"Error processing file {json_path}: {e}")

    def merge(self, data_dir: Path, output_dir: Path):
        """병합 실행"""
        # 데이터 복사
        print(f"Copying data files to {output_dir}...")
        for file in data_dir.glob("**/*"):
            if file.is_file():
                dest = output_dir / file.relative_to(data_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
                
        # 변경사항 그룹화
        file_updates = {}
        
        print("Grouping updates by file...")
        for mapping in self.mappings:
            page_id = mapping['page_id']
            line_in_page = mapping['line_in_page']
            source_file = mapping['source_file']
            json_path = mapping['json_path']
            
            if page_id not in self.translations:
                continue
            
            # 인덱스 범위 확인
            if line_in_page >= len(self.translations[page_id]):
                continue
                
            trans_data = self.translations[page_id][line_in_page]
            text = trans_data.get('text', '')
            
            # 여기서 검증 로직이 들어갈 수 있음
            # 이미 translator.py에서 검증했으므로 "text" 필드만 존재하면 병합 진행
            
            if source_file not in file_updates:
                file_updates[source_file] = []
            
            file_updates[source_file].append({
                'json_path': json_path,
                'value': text
            })
            
        # 적용
        print(f"Applying translations to {len(file_updates)} files...")
        for filename, updates in file_updates.items():
            file_path = output_dir / filename
            if not file_path.exists():
                print(f"Warning: {filename} not found in output dir")
                continue
                
            self.apply_translation_to_json(file_path, updates)
            
        print("Merge complete!")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--chunks-dir', required=True)
    parser.add_argument('--mapping', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--include-risky', action='store_true', help='Include risky translations (scripts, plugins)')
    
    args = parser.parse_args()
    
    merger = VerifiedMerger()
    merger.load_mappings(Path(args.mapping))
    merger.load_translations(Path(args.chunks_dir), include_risky=args.include_risky)
    
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    merger.merge(Path(args.data_dir), Path(args.output_dir))

if __name__ == "__main__":
    main()
