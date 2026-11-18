from fastapi.responses import HTMLResponse

@app.get("/portal", include_in_schema=False)
async def portal() -> HTMLResponse:
    return HTMLResponse(PORTAL_HTML)