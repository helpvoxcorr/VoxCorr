"""
Tâches de fond sans Celery.
Un threading.Thread daemon suffit pour Render Free (évite les 3 processus simultanés).
Migration vers Celery uniquement si les requêtes HTTP dépassent 100 s.
"""
import threading, traceback
from typing import Callable


def run_in_background(fn: Callable, *args, **kwargs) -> threading.Thread:
    def _wrap():
        try:
            fn(*args, **kwargs)
        except Exception:
            traceback.print_exc()
    t = threading.Thread(target=_wrap, daemon=True)
    t.start()
    return t
