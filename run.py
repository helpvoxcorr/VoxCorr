from app import create_app
app = create_app()

if __name__ == '__main__':
    import os
    # DEBUG activé uniquement si FLASK_DEBUG=true dans .env
    # Sur Render : ne pas définir cette variable → False en production
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug)