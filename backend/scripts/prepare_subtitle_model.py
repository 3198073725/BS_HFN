"""提前下载字幕模型到项目目录，便于迁移和离线演示。"""
import argparse
from pathlib import Path
from faster_whisper.utils import download_model


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='small')
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[2] / 'tools' / f'whisper-{args.model}'
    download_model(args.model, output_dir=str(target))
    print(f'模型准备完成：{target}')
    print(f'请在 backend/.env 设置 WHISPER_MODEL={target.as_posix()}')
