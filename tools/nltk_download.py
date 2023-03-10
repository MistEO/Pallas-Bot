from pathlib import Path
import nltk
output = Path(__file__).parent.parent / 'resource' / 'tts' / 'models' / 'nltk_data'
nltk.download('cmudict', download_dir=output)