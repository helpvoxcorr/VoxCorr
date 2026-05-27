from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db       = SQLAlchemy()
migrate  = Migrate()
login_manager = LoginManager()

# Redirige vers login si @login_required échoue
login_manager.login_view     = "auth.login"
login_manager.login_message  = "Connectez-vous pour accéder à cette page."
login_manager.login_message_category = "warning"