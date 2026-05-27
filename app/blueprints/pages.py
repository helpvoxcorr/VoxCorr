from flask import Blueprint, render_template

pages_bp = Blueprint('pages', __name__, url_prefix='/pages')

@pages_bp.route('/documentation')
def documentation():
    return render_template('pages/documentation.html')

@pages_bp.route('/aide')
def aide():
    return render_template('pages/aide.html')

@pages_bp.route('/mentions-legales')
def mentions_legales():
    return render_template('pages/mentions_legales.html')

@pages_bp.route('/rgpd')
def rgpd():
    return render_template('pages/rgpd.html')

@pages_bp.route('/contact')
def contact():
    return render_template('pages/contact.html')

@pages_bp.route('/licence')
def licence():
    return render_template('pages/licence.html')