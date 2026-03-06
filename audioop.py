try:
    import audioop as _audioop
    from audioop import *
except Exception:
    try:
        from pyaudioop import *
    except Exception:
        raise ImportError(
            "The 'audioop' C extension is not available in this Python build and 'pyaudioop' is not installable from PyPI.\n"
            "Please use a Python build that includes 'audioop' (e.g., install official CPython from python.org or Homebrew's 'python'), "
            "then recreate your virtualenv. On macOS try: `brew install python` and reinstall dependencies."
        )
