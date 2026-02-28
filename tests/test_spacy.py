import sys
print(f"Python Executable: {sys.executable}")
try:
    import spacy
    print("spaCy imported successfully!")
    print(f"spaCy version: {spacy.__version__}")
    try:
        nlp = spacy.load("en_core_web_sm")
        print("Model 'en_core_web_sm' loaded successfully!")
    except Exception as e:
        print(f"Failed to load model: {e}")
except ImportError as e:
    print(f"Failed to import spaCy: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
