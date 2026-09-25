import os
import shutil
import argparse

def clean_output_directory():
    """
    trans4/output 폴더 내의 모든 파일과 하위 폴더를 삭제합니다.
    사용자 확인을 거친 후 작업을 수행합니다.
    """
    parser = argparse.ArgumentParser(description="trans4/output 폴더 청소 도구")
    parser.add_argument("-y", "--yes", "--force", action="store_true", help="확인 절차 없이 즉시 삭제")
    args = parser.parse_args()

    # 스크립트 파일의 위치를 기준으로 output 폴더 경로 설정
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, 'output')

    print(f"대상 디렉토리: {output_dir}")

    if not os.path.exists(output_dir):
        print("output 폴더가 존재하지 않습니다.")
        return

    # 폴더 내 항목 확인
    items = os.listdir(output_dir)
    if not items:
        print("output 폴더가 이미 비어있습니다.")
        return

    print(f"\n다음 폴더 내의 모든 파일과 하위 폴더가 삭제됩니다:\n{output_dir}")
    print("\n[삭제 대상 파일 예시]")
    for item in items[:5]:
        print(f"- {item}")
    if len(items) > 5:
        print(f"... 외 {len(items) - 5}개 항목")

    # 사용자 확인 (강제 옵션이 없을 경우에만)
    if not args.yes:
        while True:
            try:
                response = input("\n정말로 삭제하시겠습니까? (y/n): ").strip().lower()
                if response in ['y', 'yes']:
                    break
                elif response in ['n', 'no']:
                    print("작업이 취소되었습니다.")
                    return
                else:
                    print("y 또는 n을 입력해주세요.")
            except EOFError:
                print("\n입력을 받을 수 없는 환경입니다. 확인 절차를 생략하려면 -y 또는 --force 옵션을 사용하세요.")
                return

    # 삭제 수행
    print("\n삭제 작업 시작...")
    deleted_count = 0
    error_count = 0

    for item in items:
        item_path = os.path.join(output_dir, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
                deleted_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                deleted_count += 1
        except Exception as e:
            print(f"삭제 실패: {item_path} - {e}")
            error_count += 1

    print(f"\n작업 완료: {deleted_count}개 항목 삭제됨, {error_count}개 에러 발생.")
    print(f"이제 {output_dir} 폴더가 비워졌습니다.")

if __name__ == "__main__":
    clean_output_directory()
