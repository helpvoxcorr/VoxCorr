"""Lance l'application en mode développement : base SQLite locale (.env.dev), jamais la production."""
import os
import runpy

os.environ['VOXCORR_ENV'] = 'dev'
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run.py'), run_name='__main__')