from pathlib import Path
import sys
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()


SOURCE_DIR = Path(__file__).resolve().parent / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

if __name__ == "__main__":
    from civtools.main import main
    main()
