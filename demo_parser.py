from pathlib import Path
from parser import SoldOutPostParser

BASE_DIR = Path(__file__).resolve().parent

parser = SoldOutPostParser.from_csv(
    BASE_DIR / "data" / "goods.csv",
    BASE_DIR / "data" / "events.csv",
)

sample = """#ICEx
『ICEx Fourth Concert Tour 2026 ''FRESHest!!''』
@大阪・NHK大阪ホール Day1
【完売情報】
・ペンライト
・うちわ（阿久根）
・Tシャツ（M）
本日分完売です！
ありがとうございます。"""

print(parser.parse(sample).to_dict())
