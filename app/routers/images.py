"""Local image serving (F18).

`GET /images/:filename` streams a content-addressed image from
`{data_dir}/images`. Registered on the public app so the frontend fetches images
from the same origin as `/events`.
"""
#region: imports
from robyn import Response, serve_file

from app.services.images import resolve
#endregion


#region: routes
def register(app) -> None:
    @app.get("/images/:filename")
    def image(request):
        filename = request.path_params.get("filename", "")
        path = resolve(filename)
        if path is None or not path.is_file():
            return Response(status_code=404, headers={}, description="")
        return serve_file(str(path), file_name=filename)
#endregion
