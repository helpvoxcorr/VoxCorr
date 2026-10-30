from flask import request, url_for

BREADCRUMB_MAP = {
    'teacher_crud.dashboard': {'label': 'Tableau de bord', 'icon': 'bi-house-door'},
    'teacher_crud.classes': {'label': 'Classes', 'parent': 'teacher_crud.dashboard'},
    'teacher_crud.class_detail': {'label': 'Classe', 'parent': 'teacher_crud.classes'},
    'teacher_crud.new_class': {'label': 'Nouvelle classe', 'parent': 'teacher_crud.classes'},
    'teacher_crud.edit_class': {'label': 'Modifier classe', 'parent': 'teacher_crud.classes'},
    'teacher_crud.new_assignment': {'label': 'Nouveau devoir', 'parent': 'teacher_crud.class_detail'},
    'teacher_crud.edit_assignment': {'label': 'Modifier devoir', 'parent': 'teacher_crud.class_detail'},
    'teacher_corr.assignment_corrections': {'label': 'Corrections', 'parent': 'teacher_crud.class_detail'},
    'teacher_corr.record': {'label': 'Correction orale', 'parent': 'teacher_corr.assignment_corrections'},
    'teacher_corr.correction_detail': {'label': 'Détail correction', 'parent': 'teacher_corr.assignment_corrections'},
    'teacher_admin.admin': {'label': 'Administration', 'parent': 'teacher_crud.dashboard'},
    'teacher_admin.access_codes': {'label': "Codes d'accès", 'parent': 'teacher_admin.admin'},
}

def build_breadcrumb(endpoint, context=None):
    if context is None:
        context = {}
    
    breadcrumb = []
    current = endpoint
    
    # Extraire les paramètres de l'URL actuelle pour les réutiliser
    url_params = {}
    if hasattr(request, 'view_args') and request.view_args:
        url_params.update(request.view_args)
    
    while current and current in BREADCRUMB_MAP:
        config = BREADCRUMB_MAP[current]
        label = config.get('label', current)
        
        if callable(label):
            label = label(context)
        
        # Construire l'URL avec les paramètres disponibles
        url = None
        if current != endpoint:
            try:
                # Filtrer les paramètres nécessaires pour cet endpoint
                params = {k: v for k, v in url_params.items() if k in ['class_id', 'assignment_id', 'student_id', 'correction_id']}
                url = url_for(current, **params)
            except Exception:
                url = None
        
        breadcrumb.insert(0, {
            'label': label,
            'url': url,
            'icon': config.get('icon')
        })
        
        current = config.get('parent')
    
    if breadcrumb:
        breadcrumb[-1]['url'] = None
    
    return breadcrumb