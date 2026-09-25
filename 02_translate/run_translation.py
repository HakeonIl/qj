import os
import sys
import subprocess
from pathlib import Path

def run_translation():
    """번역 프로세스를 실행하는 래퍼 스크립트"""
    
    # 현재 스크립트의 위치를 기준으로 경로 설정
    base_dir = Path(__file__).parent.parent # trans4 폴더
    translator_script = base_dir / "02_translate" / "translator.py"
    input_file = base_dir / "output" / "japanese_texts.txt"
    
    # 파일 존재 확인
    if not input_file.exists():
        print(f"Error: 입력 파일이 없습니다. ({input_file})")
        print("먼저 추출(Extraction) 단계를 실행해주세요.")
        return

    print("=== 번역 프로세스 시작 ===")
    print(f"Target Input: {input_file}")
    
    # 명령어 실행
    try:
        cmd = [sys.executable, str(translator_script), "--input-file", str(input_file)]
        subprocess.run(cmd, check=True)
        print("\n=== 번역 프로세스 완료 ===")
        
    except subprocess.CalledProcessError as e:
        print(f"\nError: 번역 스크립트 실행 중 오류가 발생했습니다. (Exit Code: {e.returncode})")
    except Exception as e:
        print(f"\nError: 예상치 못한 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    run_translation()
