from django.views.generic import TemplateView
def serve_sw(request):
    from django.http import FileResponse
    import os
    path = os.path.join(settings.STATIC_ROOT, "pwa", "sw.js")
    return FileResponse(open(path, "rb"), content_type="application/javascript")

def serve_manifest(request):
    from django.http import FileResponse
    import os
    path = os.path.join(settings.STATIC_ROOT, "pwa", "manifest.json")
    return FileResponse(open(path, "rb"), content_type="application/manifest+json")